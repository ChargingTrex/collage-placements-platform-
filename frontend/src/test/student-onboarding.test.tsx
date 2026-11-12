import '@testing-library/jest-dom/vitest'
import { render, screen, waitFor, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

import App from '@/App'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import type { Onboarding } from '@/api/profiles'
import { makeOwnProfile } from '@/test/fixtures'
import { HEALTHY, makeAuthResult, makeUser, mockApi, renderApp, type Route } from '@/test/harness'

const FORM: Onboarding = {
  completed: false,
  dismissed: false,
  student: {
    prn: '220200901',
    full_name: 'Aarav Mehta',
    email: 'aarav.mehta@college.edu',
    department: 'Computer Engineering',
    school: 'computing_data_science',
    batch: 2026,
    year_of_study: 4,
  },
  phone: '',
  personal_email: '',
  career_path: 'undecided',
  career_path_detail: '',
  also_attending_placements: false,
  headline: '',
  summary: '',
}

function signedInAsStudent(extra: Route[] = []) {
  localStorage.setItem('pcp.access', 'access-token')
  return mockApi([
    HEALTHY,
    { path: '/api/auth/me', body: makeUser() },
    ...extra,
    { path: '/api/profiles/me', method: 'GET', body: makeOwnProfile() },
  ])
}

beforeEach(() => localStorage.clear())
afterEach(() => {
  vi.unstubAllGlobals()
  localStorage.clear()
})

describe('onboarding', () => {
  it('shows roster facts read-only and submits the form', async () => {
    const user = userEvent.setup()
    const sent: unknown[] = []
    signedInAsStudent([
      { path: '/api/profiles/me/onboarding', method: 'GET', body: FORM },
      {
        path: '/api/profiles/me/onboarding',
        method: 'POST',
        body: { ...FORM, completed: true },
        onCall: ({ body }) => sent.push(body),
      },
    ])
    renderApp('/student/onboarding')

    const record = (await screen.findByText('Your college record')).closest('section')!
    expect(within(record).getByText('220200901')).toBeInTheDocument()
    expect(within(record).getByText('aarav.mehta@college.edu')).toBeInTheDocument()
    expect(screen.queryByLabelText('Name')).not.toBeInTheDocument()

    await user.type(screen.getByLabelText('Phone'), '9820011001')
    await user.click(screen.getByRole('radio', { name: /^Higher studies/ }))
    await user.click(screen.getByRole('button', { name: 'Save and continue' }))

    await waitFor(() => expect(sent).toHaveLength(1))
    expect(sent[0]).toMatchObject({
      phone: '9820011001',
      career_path: 'higher_studies',
      personal_email: '',
    })
    expect(await screen.findByText(/Hello, Aarav/)).toBeInTheDocument()
  })

  it('offers an optional transcript upload and completes without one', async () => {
    const user = userEvent.setup()
    const sent: unknown[] = []
    signedInAsStudent([
      { path: '/api/profiles/me/onboarding', method: 'GET', body: FORM },
      {
        path: '/api/profiles/me/onboarding',
        method: 'POST',
        body: { ...FORM, completed: true },
        onCall: ({ body }) => sent.push(body),
      },
    ])
    renderApp('/student/onboarding')

    expect(await screen.findByLabelText('Upload transcript')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Upload' })).toBeDisabled()

    await user.type(screen.getByLabelText('Phone'), '9820011001')
    await user.click(screen.getByRole('radio', { name: /^Higher studies/ }))
    await user.click(screen.getByRole('button', { name: 'Save and continue' }))

    await waitFor(() => expect(sent).toHaveLength(1))
    expect(await screen.findByText(/Hello, Aarav/)).toBeInTheDocument()
  })

  it('uploads the transcript on its own through POST me/transcript', async () => {
    const user = userEvent.setup()
    const uploads: unknown[] = []
    signedInAsStudent([
      { path: '/api/profiles/me/onboarding', method: 'GET', body: FORM },
      {
        path: '/api/profiles/me/transcript',
        method: 'POST',
        body: makeOwnProfile({
          transcript_url: '/api/profiles/me/transcript',
          transcript_filename: 'transcript.pdf',
        }),
        onCall: ({ body }) => uploads.push(body),
      },
    ])
    renderApp('/student/onboarding')

    const input = await screen.findByLabelText('Upload transcript')
    await user.upload(input, new File(['%PDF'], 'transcript.pdf', { type: 'application/pdf' }))
    await user.click(screen.getByRole('button', { name: 'Upload' }))

    expect(await screen.findByText('transcript.pdf')).toBeInTheDocument()
    expect(uploads).toHaveLength(1)
    // Still on the onboarding form: uploading does not submit it.
    expect(screen.getByRole('button', { name: 'Save and continue' })).toBeInTheDocument()
  })

  it('requires a phone number and a career path before sending anything', async () => {
    const user = userEvent.setup()
    const sent: unknown[] = []
    signedInAsStudent([
      { path: '/api/profiles/me/onboarding', method: 'GET', body: FORM },
      { path: '/api/profiles/me/onboarding', method: 'POST', onCall: ({ body }) => sent.push(body) },
    ])
    renderApp('/student/onboarding')

    await user.click(await screen.findByRole('button', { name: 'Save and continue' }))
    expect(await screen.findByText('Enter your phone number.')).toBeInTheDocument()

    await user.type(screen.getByLabelText('Phone'), '9820011001')
    await user.click(screen.getByRole('button', { name: 'Save and continue' }))
    expect(
      await screen.findByText('Choose what you plan to do after graduation.'),
    ).toBeInTheDocument()

    await user.click(screen.getByRole('radio', { name: /^Other/ }))
    await user.click(screen.getByRole('button', { name: 'Save and continue' }))
    expect(await screen.findByText('Tell us what "Other" means.')).toBeInTheDocument()
    expect(sent).toEqual([])
  })

  it('shows the server message when the personal email is the college email', async () => {
    const user = userEvent.setup()
    signedInAsStudent([
      { path: '/api/profiles/me/onboarding', method: 'GET', body: FORM },
      {
        path: '/api/profiles/me/onboarding',
        method: 'POST',
        status: 400,
        body: { personal_email: ['Use an address other than your college email.'] },
      },
    ])
    renderApp('/student/onboarding')

    await user.type(await screen.findByLabelText('Phone'), '9820011001')
    await user.type(screen.getByLabelText(/Personal email/), 'aarav.mehta@college.edu')
    await user.click(screen.getByRole('radio', { name: /^Placement/ }))
    await user.click(screen.getByRole('button', { name: 'Save and continue' }))

    expect(
      await screen.findByText('Use an address other than your college email.'),
    ).toBeInTheDocument()
    // Still on the form: nothing was completed.
    expect(screen.getByRole('button', { name: 'Save and continue' })).toBeInTheDocument()
  })

  it('can be skipped, and the dashboard keeps the banner', async () => {
    const user = userEvent.setup()
    let dismissed = 0
    signedInAsStudent([
      { path: '/api/profiles/me/onboarding', method: 'GET', body: FORM },
      {
        path: '/api/profiles/me/onboarding/dismiss',
        method: 'POST',
        status: 204,
        onCall: () => (dismissed += 1),
      },
    ])
    renderApp('/student/onboarding')

    await user.click(await screen.findByRole('button', { name: 'Skip for now' }))

    expect(await screen.findByText('Finish setting up your account')).toBeInTheDocument()
    expect(dismissed).toBe(1)
    expect(screen.getByRole('link', { name: 'Complete the short form' })).toHaveAttribute(
      'href',
      '/student/onboarding',
    )
  })

  it('does not show the banner, or the form, once completed', async () => {
    signedInAsStudent([
      { path: '/api/profiles/me/onboarding', method: 'GET', body: { ...FORM, completed: true } },
      {
        path: '/api/profiles/me',
        method: 'GET',
        body: makeOwnProfile({ onboarding_completed: true }),
      },
    ])
    renderApp('/student/onboarding')

    expect(await screen.findByText(/Hello, Aarav/)).toBeInTheDocument()
    await waitFor(() =>
      expect(screen.queryByText('Finish setting up your account')).not.toBeInTheDocument(),
    )
  })
})

describe('signup verification', () => {
  it('sends a newly verified student to the onboarding form', async () => {
    const user = userEvent.setup()
    mockApi([
      HEALTHY,
      { path: '/api/auth/verify', body: makeAuthResult() },
      { path: '/api/auth/me', body: makeUser() },
      { path: '/api/profiles/me/onboarding', method: 'GET', body: FORM },
    ])
    render(
      <MemoryRouter
        initialEntries={[{ pathname: '/verify', state: { identifier: '220200901', debugOtp: '123456' } }]}
      >
        <App />
      </MemoryRouter>,
    )

    await user.type(await screen.findByLabelText('Choose a password'), 'StudentPass!234')
    await user.click(screen.getByRole('button', { name: /verify and continue/i }))

    expect(await screen.findByText('Welcome. A few details first.')).toBeInTheDocument()
  })
})
