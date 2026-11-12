import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { makeOwnProfile } from '@/test/fixtures'
import { HEALTHY, makeUser, mockApi, renderApp, type Route } from '@/test/harness'

const STUDENT = makeUser()

function signedInAsStudent(extra: Route[] = []) {
  localStorage.setItem('pcp.access', 'access-token')
  // Later routes win only if listed first, so `extra` is placed ahead of the
  // catch-all profile route.
  return mockApi([HEALTHY, { path: '/api/auth/me', body: STUDENT }, ...extra])
}

beforeEach(() => localStorage.clear())
afterEach(() => {
  vi.unstubAllGlobals()
  localStorage.clear()
})

describe('student profile', () => {
  it('shows the roster facts as a read-only college record', async () => {
    signedInAsStudent([{ path: '/api/profiles/me', body: makeOwnProfile() }])
    renderApp('/student/profile')

    await waitFor(() => expect(screen.getByText('College record')).toBeInTheDocument())
    const card = screen.getByText('College record').closest('section')!
    expect(within(card).getByText('220200901')).toBeInTheDocument()
    expect(within(card).getByText('Computer Engineering')).toBeInTheDocument()
    expect(within(card).getByText('8.72')).toBeInTheDocument()
    // The roster's figure is a record, not a field. The student states their
    // own CGPA in its own card; this one they cannot edit.
    expect(within(card).queryByLabelText(/cgpa/i)).not.toBeInTheDocument()
    expect(within(card).queryByRole('textbox')).not.toBeInTheDocument()
  })

  it('lists what is still missing from the profile', async () => {
    signedInAsStudent([{ path: '/api/profiles/me', body: makeOwnProfile() }])
    renderApp('/student/profile')

    await waitFor(() => expect(screen.getByText('Profile completion')).toBeInTheDocument())
    expect(screen.getByText('0 of 7 done')).toBeInTheDocument()
    expect(screen.getByText('At least three skills')).toBeInTheDocument()
  })

  it('saves the headline and summary', async () => {
    const user = userEvent.setup()
    const calls: Array<{ method: string; body: unknown }> = []
    signedInAsStudent([
      {
        path: '/api/profiles/me',
        method: 'PATCH',
        body: makeOwnProfile({ headline: 'Backend developer', completion_percent: 14 }),
        onCall: (call) => calls.push(call),
      },
      { path: '/api/profiles/me', method: 'GET', body: makeOwnProfile() },
    ])
    renderApp('/student/profile')

    await waitFor(() => expect(screen.getByLabelText(/headline/i)).toBeInTheDocument())
    await user.type(screen.getByLabelText(/headline/i), 'Backend developer')
    await user.click(screen.getByRole('button', { name: /^save$/i }))

    await waitFor(() => expect(screen.getByText('Saved.')).toBeInTheDocument())
    const patch = calls.find((call) => call.method === 'PATCH')!
    expect((patch.body as Record<string, string>).headline).toBe('Backend developer')
  })

  it('warns when "shortlisted only" is hiding the profile from everyone', async () => {
    signedInAsStudent([
      {
        path: '/api/profiles/me',
        body: makeOwnProfile({ visibility: 'shortlisted', shortlisted_by_count: 0 }),
      },
    ])
    renderApp('/student/profile')

    await waitFor(() =>
      expect(screen.getByText(/no company can see your profile right now/i)).toBeInTheDocument(),
    )
    expect(screen.getByText(/none have yet/i)).toBeInTheDocument()
    expect(
      screen.getByRole('button', { name: /make my profile visible to all companies/i }),
    ).toBeInTheDocument()
  })

  it('does not warn when companies have actually shortlisted the student', async () => {
    signedInAsStudent([
      {
        path: '/api/profiles/me',
        body: makeOwnProfile({ visibility: 'shortlisted', shortlisted_by_count: 2 }),
      },
    ])
    renderApp('/student/profile')

    await waitFor(() => expect(screen.getByText('Who can see this')).toBeInTheDocument())
    expect(screen.queryByText(/no company can see your profile right now/i)).not.toBeInTheDocument()
    expect(screen.getByText(/2 companies have shortlisted you/i)).toBeInTheDocument()
  })

  it('switches back to all companies in one click', async () => {
    const user = userEvent.setup()
    const calls: Array<{ method: string; body: unknown }> = []
    signedInAsStudent([
      {
        path: '/api/profiles/me/visibility',
        body: { visibility: 'all' },
        onCall: (call) => calls.push(call),
      },
      {
        path: '/api/profiles/me',
        body: makeOwnProfile({ visibility: 'shortlisted', shortlisted_by_count: 0 }),
      },
    ])
    renderApp('/student/profile')

    await waitFor(() =>
      expect(
        screen.getByRole('button', { name: /make my profile visible to all companies/i }),
      ).toBeInTheDocument(),
    )
    await user.click(
      screen.getByRole('button', { name: /make my profile visible to all companies/i }),
    )

    await waitFor(() => expect(calls).toHaveLength(1))
    expect(calls[0].body).toEqual({ visibility: 'all' })
  })

  it('warns when the profile is hidden outright', async () => {
    signedInAsStudent([
      { path: '/api/profiles/me', body: makeOwnProfile({ visibility: 'hidden' }) },
    ])
    renderApp('/student/profile')

    await waitFor(() =>
      expect(screen.getByText(/hidden from every company/i)).toBeInTheDocument(),
    )
  })

  it('changes visibility through the server, not just in the page', async () => {
    const user = userEvent.setup()
    const calls: Array<{ method: string; body: unknown }> = []
    signedInAsStudent([
      {
        path: '/api/profiles/me/visibility',
        body: { visibility: 'hidden' },
        onCall: (call) => calls.push(call),
      },
      { path: '/api/profiles/me', body: makeOwnProfile({ visibility: 'all' }) },
    ])
    renderApp('/student/profile')

    await waitFor(() => expect(screen.getByText('Who can see this')).toBeInTheDocument())
    await user.click(screen.getByRole('radio', { name: /hidden/i }))

    await waitFor(() => expect(calls).toHaveLength(1))
    expect(calls[0].method).toBe('PUT')
    expect(calls[0].body).toEqual({ visibility: 'hidden' })
  })
})

describe('resume upload and review', () => {
  const UPLOADED = makeOwnProfile({
    resume_filename: 'aarav_mehta_backend.pdf',
    resume_uploaded_at: '2026-09-23T10:00:00Z',
    experience_years: '3.0',
    education_level: 'UG',
    parsed_experience_years: '3.0',
    parsed_education_levels: ['UG'],
    parsed_values_confirmed: false,
    completion_percent: 14,
  })

  it('pre-fills experience and education from the parsed resume', async () => {
    const user = userEvent.setup()
    signedInAsStudent([
      {
        path: '/api/profiles/me/resume',
        status: 201,
        body: {
          suggestion: { experience_years: 3, education_level: 'UG', applied: true },
          profile: UPLOADED,
        },
      },
      { path: '/api/profiles/me', body: makeOwnProfile() },
    ])
    renderApp('/student/profile')

    await waitFor(() => expect(screen.getByLabelText(/upload resume/i)).toBeInTheDocument())
    await user.upload(
      screen.getByLabelText(/upload resume/i),
      new File(['%PDF-1.4'], 'aarav_mehta_backend.pdf', { type: 'application/pdf' }),
    )

    await waitFor(() =>
      expect(screen.getByText(/filled them in below/i)).toBeInTheDocument(),
    )
    expect(screen.getByLabelText(/years of experience/i)).toHaveValue(3)
    expect(screen.getByLabelText(/education level/i)).toHaveValue('UG')
    expect(screen.getByText(/needs your check/i)).toBeInTheDocument()
  })

  it('lets the student correct the parsed values before confirming', async () => {
    const user = userEvent.setup()
    const calls: Array<{ method: string; body: unknown }> = []
    signedInAsStudent([
      {
        path: '/api/profiles/me/confirm-parsed',
        body: makeOwnProfile({ ...UPLOADED, experience_years: '1.5', parsed_values_confirmed: true }),
        onCall: (call) => calls.push(call),
      },
      { path: '/api/profiles/me', body: UPLOADED },
    ])
    renderApp('/student/profile')

    await waitFor(() =>
      expect(screen.getByLabelText(/years of experience/i)).toBeInTheDocument(),
    )
    const yearsField = screen.getByLabelText(/years of experience/i)
    await user.clear(yearsField)
    await user.type(yearsField, '1.5')
    await user.click(screen.getByRole('button', { name: /these are correct/i }))

    await waitFor(() => expect(calls).toHaveLength(1))
    expect(calls[0].body).toEqual({ experience_years: '1.5', education_level: 'UG' })
  })

  it('says the students own value was kept when a later resume disagrees', async () => {
    const user = userEvent.setup()
    signedInAsStudent([
      {
        path: '/api/profiles/me/resume',
        status: 201,
        body: {
          suggestion: { experience_years: 4, education_level: 'UG', applied: false },
          profile: makeOwnProfile({
            ...UPLOADED,
            experience_years: '1.0',
            parsed_experience_years: '4.0',
            parsed_values_confirmed: true,
            parsed_differs_from_confirmed: true,
          }),
        },
      },
      { path: '/api/profiles/me', body: makeOwnProfile({ ...UPLOADED, parsed_values_confirmed: true }) },
    ])
    renderApp('/student/profile')

    await waitFor(() => expect(screen.getByLabelText(/replace resume/i)).toBeInTheDocument())
    await user.upload(
      screen.getByLabelText(/replace resume/i),
      new File(['%PDF-1.4'], 'other.pdf', { type: 'application/pdf' }),
    )

    await waitFor(() => expect(screen.getByText(/yours has been kept/i)).toBeInTheDocument())
  })

  it('reports an unreadable file without losing the stored one', async () => {
    const user = userEvent.setup()
    signedInAsStudent([
      {
        path: '/api/profiles/me/resume',
        status: 400,
        body: { detail: 'Could not read the PDF: EOF marker not found' },
      },
      { path: '/api/profiles/me', body: UPLOADED },
    ])
    renderApp('/student/profile')

    await waitFor(() => expect(screen.getByLabelText(/replace resume/i)).toBeInTheDocument())
    await user.upload(
      screen.getByLabelText(/replace resume/i),
      new File(['junk'], 'broken.pdf', { type: 'application/pdf' }),
    )

    await waitFor(() => expect(screen.getByText(/could not read the pdf/i)).toBeInTheDocument())
    expect(screen.getByText('aarav_mehta_backend.pdf')).toBeInTheDocument()
  })
})
