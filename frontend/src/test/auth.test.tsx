import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { HEALTHY, makeAuthResult, makeUser, mockApi, renderApp } from '@/test/harness'

afterEach(() => {
  vi.unstubAllGlobals()
  localStorage.clear()
})

describe('student signup', () => {
  it('sends PRN and email, then moves to the verification step', async () => {
    const user = userEvent.setup()
    const calls: Array<{ method: string; body: unknown }> = []
    mockApi([
      HEALTHY,
      {
        path: '/api/auth/signup',
        status: 201,
        body: {
          detail: 'Verification code sent.',
          expires_at: '2026-09-21T10:00:00Z',
          prn: '220200901',
          email: 'aarav.mehta@college.edu',
          debug_otp: '123456',
        },
        onCall: (call) => calls.push(call),
      },
    ])
    renderApp('/signup')

    await user.type(screen.getByLabelText(/prn/i), '220200901')
    await user.type(screen.getByLabelText(/college email/i), 'aarav.mehta@college.edu')
    await user.click(screen.getByRole('button', { name: /send verification code/i }))

    await waitFor(() =>
      expect(screen.getByRole('heading', { name: /verify your email/i })).toBeInTheDocument(),
    )
    expect(calls[0].body).toEqual({ prn: '220200901', email: 'aarav.mehta@college.edu' })
    // DEBUG mode pre-fills the code so the prototype can be driven end to end.
    expect(screen.getByLabelText(/verification code/i)).toHaveValue('123456')
  })

  it('explains a roster mismatch and says it was sent for review', async () => {
    const user = userEvent.setup()
    mockApi([
      HEALTHY,
      {
        path: '/api/auth/signup',
        status: 403,
        body: {
          detail: 'That PRN is on the roster under a different email address.',
          reason: 'email_mismatch',
          flagged_for_review: true,
        },
      },
    ])
    renderApp('/signup')

    await user.type(screen.getByLabelText(/prn/i), '220200901')
    await user.type(screen.getByLabelText(/college email/i), 'wrong@college.edu')
    await user.click(screen.getByRole('button', { name: /send verification code/i }))

    await waitFor(() =>
      expect(screen.getByText(/couldn't match you to the roster/i)).toBeInTheDocument(),
    )
    expect(screen.getByText(/different email address/i)).toBeInTheDocument()
    expect(screen.getByText(/sent to the placement cell for review/i)).toBeInTheDocument()
    // The user is kept on the form rather than pushed to a dead end.
    expect(screen.getByRole('heading', { name: /create your account/i })).toBeInTheDocument()
  })

  it('cannot be reached directly without a signup behind it', async () => {
    mockApi([HEALTHY])
    renderApp('/verify')

    await waitFor(() =>
      expect(screen.getByRole('heading', { name: /create your account/i })).toBeInTheDocument(),
    )
  })
})

describe('login', () => {
  it('signs a student in with PRN and password and lands on their dashboard', async () => {
    const user = userEvent.setup()
    const calls: Array<{ method: string; body: unknown }> = []
    mockApi([
      HEALTHY,
      { path: '/api/auth/login', body: makeAuthResult(), onCall: (call) => calls.push(call) },
      { path: '/api/auth/me', body: makeUser() },
      { path: '/api/roster', body: { count: 0, results: [] } },
    ])
    renderApp('/login')

    await user.type(screen.getByLabelText(/prn or email/i), '220200901')
    await user.type(screen.getByLabelText(/^password$/i), 'StudentPass!234')
    await user.click(screen.getByRole('button', { name: /^sign in$/i }))

    await waitFor(() => expect(screen.getByText(/hello, aarav mehta/i)).toBeInTheDocument())
    expect(calls[0].body).toEqual({ identifier: '220200901', password: 'StudentPass!234' })
    expect(localStorage.getItem('pcp.access')).toBe('access-token')
  })

  it('sends an admin to the admin dashboard', async () => {
    const user = userEvent.setup()
    mockApi([
      HEALTHY,
      {
        path: '/api/auth/login',
        body: makeAuthResult({
          roles: ['placement_admin'],
          prn: null,
          email: 'placement.officer@college.edu',
          full_name: 'Priya Kulkarni',
        }),
      },
      { path: '/api/roster/students', body: { count: 11, results: [] } },
      { path: '/api/roster/flagged', body: { count: 2, results: [] } },
    ])
    renderApp('/login')

    await user.type(screen.getByLabelText(/prn or email/i), 'placement.officer@college.edu')
    await user.type(screen.getByLabelText(/^password$/i), 'AdminPass!234')
    await user.click(screen.getByRole('button', { name: /^sign in$/i }))

    await waitFor(() => expect(screen.getByText(/welcome, priya kulkarni/i)).toBeInTheDocument())
    await waitFor(() => expect(screen.getByText('11')).toBeInTheDocument())
    expect(screen.getByText('2')).toBeInTheDocument()
  })

  it('shows the server message when credentials are refused', async () => {
    const user = userEvent.setup()
    mockApi([
      HEALTHY,
      {
        path: '/api/auth/login',
        status: 401,
        body: { detail: 'Those credentials did not match an active account.' },
      },
    ])
    renderApp('/login')

    await user.type(screen.getByLabelText(/prn or email/i), '220200901')
    await user.type(screen.getByLabelText(/^password$/i), 'wrong')
    await user.click(screen.getByRole('button', { name: /^sign in$/i }))

    await waitFor(() =>
      expect(screen.getByText(/did not match an active account/i)).toBeInTheDocument(),
    )
  })

  it('can request an email code instead of using a password', async () => {
    const user = userEvent.setup()
    mockApi([
      HEALTHY,
      {
        path: '/api/auth/otp/request',
        body: { detail: 'If that PRN or email has a verified account, a code is on its way.', debug_otp: '654321' },
      },
      { path: '/api/auth/otp/login', body: makeAuthResult() },
      { path: '/api/auth/me', body: makeUser() },
    ])
    renderApp('/login')

    await user.click(screen.getByRole('tab', { name: /email code/i }))
    await user.type(screen.getByLabelText(/prn or email/i), '220200901')
    await user.click(screen.getByRole('button', { name: /email me a code/i }))

    await waitFor(() => expect(screen.getByLabelText(/code from your email/i)).toHaveValue('654321'))
    await user.click(screen.getByRole('button', { name: /^sign in$/i }))

    await waitFor(() => expect(screen.getByText(/hello, aarav mehta/i)).toBeInTheDocument())
  })
})

describe('route guards', () => {
  it('sends an anonymous visitor from a protected page to login', async () => {
    mockApi([HEALTHY])
    renderApp('/admin/roster')

    await waitFor(() => expect(screen.getByRole('heading', { name: /sign in/i })).toBeInTheDocument())
  })

  it('keeps a student out of the admin area', async () => {
    localStorage.setItem('pcp.access', 'access-token')
    mockApi([
      HEALTHY,
      { path: '/api/auth/me', body: makeUser() },
      { path: '/api/roster', body: { count: 0, results: [] } },
    ])
    renderApp('/admin/roster')

    // Bounced to their own dashboard, not shown the roster.
    await waitFor(() => expect(screen.getByText(/hello, aarav mehta/i)).toBeInTheDocument())
    expect(screen.queryByText(/upload a roster/i)).not.toBeInTheDocument()
  })

  it('discards a stale token when /me rejects it', async () => {
    localStorage.setItem('pcp.access', 'expired-token')
    mockApi([HEALTHY, { path: '/api/auth/me', status: 401, body: { detail: 'Token is invalid' } }])
    renderApp('/student')

    await waitFor(() => expect(screen.getByRole('heading', { name: /sign in/i })).toBeInTheDocument())
    expect(localStorage.getItem('pcp.access')).toBeNull()
  })
})
