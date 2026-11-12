import '@testing-library/jest-dom/vitest'
import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { STUDENT_ID } from '@/test/fixtures'
import { HEALTHY, makeUser, mockApi, renderApp, type Route } from '@/test/harness'
import { CGPA_SOURCES, makeAdminDetail } from '@/test/intelligence-fixtures'

const ADMIN = makeUser({
  roles: ['placement_admin'],
  prn: null,
  email: 'placement.officer@college.edu',
  full_name: 'Priya Kulkarni',
})

const RESUME_URL = `/api/profiles/admin/${STUDENT_ID}/resume`
const TRANSCRIPT_URL = `/api/profiles/admin/${STUDENT_ID}/transcript`

// A hidden profile with a CGPA review open: the admin sees all of it.
const DETAIL = makeAdminDetail({
  visibility: 'hidden',
  resume_url: RESUME_URL,
  transcript_url: TRANSCRIPT_URL,
  career_path: 'family_business',
  onboarding_completed: false,
  parsed_cgpa: '8.40',
  recomputed_cgpa: '8.41',
  cgpa_matches_roster: false,
  cgpa_review_status: 'open',
  // The panel renders the server's comparison, so the fixture has to carry
  // the same figures the fields above do.
  cgpa_sources: {
    ...CGPA_SOURCES,
    values: {
      roster: 8.72,
      transcript_printed: 8.4,
      transcript_recomputed: 8.41,
      student: null,
    },
    disagreements: [
      {
        sources: ['roster', 'transcript_printed'],
        values: { roster: 8.72, transcript_printed: 8.4 },
        message: 'Roster (8.72) and Printed on transcript (8.4) differ by more than 0.1.',
      },
    ],
  },
})

const openedTab = { location: { href: '' }, close: vi.fn() }

function signedInAsAdmin(extra: Route[] = []) {
  localStorage.setItem('pcp.access', 'access-token')
  return mockApi([
    HEALTHY,
    { path: '/api/auth/me', body: ADMIN },
    ...extra,
    { path: `/api/profiles/admin/${STUDENT_ID}`, method: 'GET', body: DETAIL },
  ])
}

beforeEach(() => {
  localStorage.clear()
  openedTab.location.href = ''
  openedTab.close.mockClear()
  vi.stubGlobal('open', vi.fn(() => openedTab))
  URL.createObjectURL = vi.fn(() => 'blob:resume')
})
afterEach(() => {
  vi.unstubAllGlobals()
  localStorage.clear()
})

describe('admin profile detail', () => {
  it('shows a hidden profile in full, with career path and CGPA figures', async () => {
    signedInAsAdmin()
    renderApp(`/admin/profiles/${STUDENT_ID}`)

    expect(await screen.findByRole('heading', { name: 'Aarav Mehta' })).toBeInTheDocument()
    expect(screen.getByText('hidden')).toBeInTheDocument()
    expect(screen.getByText('Taking over family business')).toBeInTheDocument()
    expect(screen.getByText('Onboarding pending')).toBeInTheDocument()
    expect(screen.getByText('8.40')).toBeInTheDocument()
    expect(screen.getByText('8.41')).toBeInTheDocument()
    expect(screen.getByText('Differs from the roster')).toBeInTheDocument()
  })

  it('opens the resume through the bearer token, not a bare link', async () => {
    const user = userEvent.setup()
    const calls: Array<string | null> = []
    signedInAsAdmin([
      {
        path: RESUME_URL,
        onCall: ({ authorization }) => calls.push(authorization),
      },
    ])
    renderApp(`/admin/profiles/${STUDENT_ID}`)

    await user.click(await screen.findByRole('button', { name: 'Open resume' }))

    await waitFor(() => expect(openedTab.location.href).toBe('blob:resume'))
    expect(calls).toEqual(['Bearer access-token'])
    expect(screen.queryByRole('link', { name: /resume/i })).not.toBeInTheDocument()
  })

  it('downloads the resume under the name the server sent', async () => {
    const user = userEvent.setup()
    const names: string[] = []
    vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(function (
      this: HTMLAnchorElement,
    ) {
      names.push(this.download)
    })
    signedInAsAdmin([
      { path: RESUME_URL, headers: { 'Content-Disposition': 'attachment; filename="aarav_cv.pdf"' } },
    ])
    renderApp(`/admin/profiles/${STUDENT_ID}`)

    const downloads = await screen.findAllByRole('button', { name: 'Download' })
    await user.click(downloads[0])

    await waitFor(() => expect(names).toEqual(['aarav_cv.pdf']))
  })

  it('says so when the document is gone', async () => {
    const user = userEvent.setup()
    signedInAsAdmin([{ path: TRANSCRIPT_URL, status: 404, body: { detail: 'Not found.' } }])
    renderApp(`/admin/profiles/${STUDENT_ID}`)

    await user.click(await screen.findByRole('button', { name: 'Open transcript' }))

    expect(await screen.findByText('This document is no longer available.')).toBeInTheDocument()
    expect(openedTab.close).toHaveBeenCalled()
  })

  it('resolves an open CGPA review', async () => {
    const user = userEvent.setup()
    const sent: unknown[] = []
    signedInAsAdmin([
      {
        path: `/api/profiles/admin/${STUDENT_ID}/cgpa-review`,
        method: 'POST',
        body: { ...DETAIL, cgpa_review_status: 'resolved' },
        onCall: ({ body }) => sent.push(body),
      },
    ])
    renderApp(`/admin/profiles/${STUDENT_ID}`)

    await user.click(await screen.findByRole('button', { name: 'Resolve' }))

    expect(await screen.findByText('Resolved')).toBeInTheDocument()
    expect(sent).toEqual([{ status: 'resolved', note: '' }])
    expect(screen.queryByRole('button', { name: 'Resolve' })).not.toBeInTheDocument()
  })
})
