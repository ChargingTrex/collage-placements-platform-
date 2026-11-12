import '@testing-library/jest-dom/vitest'
import { screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { makeOwnProfile } from '@/test/fixtures'
import { HEALTHY, makeUser, mockApi, renderApp, type Route } from '@/test/harness'

function signedInAsStudent(extra: Route[] = []) {
  localStorage.setItem('pcp.access', 'access-token')
  return mockApi([HEALTHY, { path: '/api/auth/me', body: makeUser() }, ...extra])
}

const PDF = new File(['%PDF-1.4'], 'grade_card.pdf', { type: 'application/pdf' })

const READ = makeOwnProfile({
  transcript_url: '/api/profiles/me/transcript/file',
  transcript_filename: 'grade_card.pdf',
  transcript_prn: '220200901',
  transcript_school: 'School of Computing and Data Science',
  transcript_degree: 'B.Tech Computer Engineering',
  parsed_cgpa: '8.40',
  recomputed_cgpa: '8.41',
  cgpa_matches_roster: true,
  cgpa_review_status: 'not_needed',
})

beforeEach(() => localStorage.clear())
afterEach(() => {
  vi.unstubAllGlobals()
  localStorage.clear()
})

async function openCard() {
  const heading = await screen.findByRole('heading', { name: 'Transcript' })
  return heading.closest('section') as HTMLElement
}

/** The CGPA entry is its own card beside the transcript, not inside it. */
async function openCgpaCard() {
  const heading = await screen.findByRole('heading', { name: 'Your CGPA' })
  return heading.closest('section') as HTMLElement
}

describe('transcript card', () => {
  it('uploads a PDF and shows what was read', async () => {
    const user = userEvent.setup()
    signedInAsStudent([
      { path: '/api/profiles/me/transcript', method: 'POST', status: 201, body: READ },
      { path: '/api/profiles/me', method: 'GET', body: makeOwnProfile() },
    ])
    renderApp('/student/profile')

    const card = await openCard()
    await user.upload(within(card).getByLabelText('Upload transcript'), PDF)
    await user.click(within(card).getByRole('button', { name: 'Upload' }))

    expect(await within(card).findByText('B.Tech Computer Engineering')).toBeInTheDocument()
    expect(within(card).getByText('8.40')).toBeInTheDocument()
    expect(within(card).getByText('8.41')).toBeInTheDocument()
    expect(within(card).getByText('8.72')).toBeInTheDocument()
    expect(within(card).queryByText(/reviewing your CGPA/)).not.toBeInTheDocument()
  })

  it('says the transcript belongs to someone else on a PRN mismatch', async () => {
    const user = userEvent.setup()
    signedInAsStudent([
      {
        path: '/api/profiles/me/transcript',
        method: 'POST',
        status: 400,
        body: { detail: 'PRN does not match.', reason: 'prn_mismatch' },
      },
      { path: '/api/profiles/me', method: 'GET', body: makeOwnProfile() },
    ])
    renderApp('/student/profile')

    const card = await openCard()
    await user.upload(within(card).getByLabelText('Upload transcript'), PDF)
    await user.click(within(card).getByRole('button', { name: 'Upload' }))

    expect(await within(card).findByText('This transcript is not yours')).toBeInTheDocument()
    expect(within(card).getByText(/was not saved/)).toBeInTheDocument()
    // Nothing was stored, so no transcript details appear.
    expect(within(card).queryByText('PRN on transcript')).not.toBeInTheDocument()
  })

  it('shows the review notice and lets the student confirm a CGPA', async () => {
    const user = userEvent.setup()
    const sent: unknown[] = []
    const open = { ...READ, cgpa_review_status: 'open' as const, cgpa_matches_roster: false }
    signedInAsStudent([
      {
        path: '/api/profiles/me/confirm-cgpa',
        method: 'POST',
        body: { ...open, confirmed_cgpa: '8.40' },
        onCall: ({ body }) => sent.push(body),
      },
      { path: '/api/profiles/me', method: 'GET', body: open },
    ])
    renderApp('/student/profile')

    const card = await openCard()
    expect(await within(card).findByText(/reviewing your CGPA/)).toBeInTheDocument()

    const cgpa = await openCgpaCard()
    await user.type(within(cgpa).getByLabelText('CGPA'), '8.40')
    await user.click(within(cgpa).getByRole('button', { name: 'Save CGPA' }))

    expect(await within(cgpa).findByText('Saved.')).toBeInTheDocument()
    expect(sent).toEqual([{ cgpa: '8.40' }])
  })

  it('shows the server message when the CGPA is out of range', async () => {
    const user = userEvent.setup()
    const open = { ...READ, parsed_cgpa: null, cgpa_review_status: 'open' as const }
    signedInAsStudent([
      {
        path: '/api/profiles/me/confirm-cgpa',
        method: 'POST',
        status: 400,
        body: { cgpa: ['CGPA must be between 0 and 10.'] },
      },
      { path: '/api/profiles/me', method: 'GET', body: open },
    ])
    renderApp('/student/profile')

    const cgpa = await openCgpaCard()
    await user.type(await within(cgpa).findByLabelText('CGPA'), '11')
    await user.click(within(cgpa).getByRole('button', { name: 'Save CGPA' }))

    expect(await within(cgpa).findByText('CGPA must be between 0 and 10.')).toBeInTheDocument()
  })
})
