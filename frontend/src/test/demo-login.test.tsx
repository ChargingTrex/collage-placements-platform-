import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { HEALTHY, makeAuthResult, mockApi, renderApp } from '@/test/harness'

const PERSONAS = {
  personas: [
    {
      key: 'student',
      label: 'Student',
      description: 'A final-year student.',
      role: 'student',
      identifier: '220200901',
    },
    {
      key: 'officer',
      label: 'Placement officer',
      description: 'The pilot placement-cell login.',
      role: 'admin',
      identifier: 'pilot.officer@college.edu',
    },
    {
      key: 'acme',
      label: 'Acme Tech recruiter',
      description: 'Recruiter.',
      role: 'company',
      identifier: 'recruiter@acmetech.example',
    },
    {
      key: 'nimbus',
      label: 'Nimbus Analytics recruiter',
      description: 'Recruiter.',
      role: 'company',
      identifier: 'talent@nimbusanalytics.example',
    },
  ],
}

afterEach(() => {
  vi.unstubAllGlobals()
  localStorage.clear()
})

describe('one-click demo sign-in', () => {
  it('shows one button per persona when the server is in demo mode', async () => {
    mockApi([HEALTHY, { path: '/api/auth/demo/personas', body: PERSONAS }])
    renderApp('/login')

    await waitFor(() =>
      expect(screen.getByRole('heading', { name: 'Demo sign-in' })).toBeInTheDocument(),
    )
    for (const label of ['Student', 'Placement officer', 'Acme Tech recruiter', 'Nimbus Analytics recruiter']) {
      expect(screen.getByRole('button', { name: new RegExp(`sign in as ${label}`, 'i') })).toBeInTheDocument()
    }
    expect(screen.getByText('pilot.officer@college.edu')).toBeInTheDocument()
  })

  it('shows no demo buttons when the endpoint answers 404, as on the public link', async () => {
    const fetchMock = mockApi([
      HEALTHY,
      { path: '/api/auth/demo/personas', status: 404, body: { detail: 'Not found.' } },
    ])
    renderApp('/login')

    await waitFor(() =>
      expect(fetchMock.mock.calls.some(([url]) => String(url) === '/api/auth/demo/personas')).toBe(true),
    )
    expect(screen.getByRole('button', { name: /^sign in$/i })).toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: 'Demo sign-in' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /sign in as/i })).not.toBeInTheDocument()
    // A 404 here is the normal case off the laptop, never an error message.
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  it('signs in as the chosen persona and lands on that role’s dashboard', async () => {
    const user = userEvent.setup()
    const calls: Array<{ body: unknown; authorization: string | null }> = []
    mockApi([
      HEALTHY,
      { path: '/api/auth/demo/personas', body: PERSONAS },
      {
        path: '/api/auth/demo/login',
        method: 'POST',
        body: makeAuthResult({
          roles: ['placement_admin'],
          prn: null,
          email: 'pilot.officer@college.edu',
          full_name: 'Anika Verma',
        }),
        onCall: (call) => calls.push(call),
      },
      { path: '/api/roster/students', body: { count: 11, results: [] } },
      { path: '/api/roster/flagged', body: { count: 0, results: [] } },
    ])
    renderApp('/login')

    await user.click(await screen.findByRole('button', { name: /sign in as placement officer/i }))

    await waitFor(() => expect(screen.getByText(/welcome, anika verma/i)).toBeInTheDocument())
    expect(calls[0].body).toEqual({ persona: 'officer' })
    // No password and no stale token travel with it.
    expect(calls[0].authorization).toBeNull()
    expect(localStorage.getItem('pcp.access')).toBe('access-token')
  })

  it.each([
    ['Student', makeAuthResult(), /hello, aarav mehta/i, '/student'],
    [
      'Placement officer',
      makeAuthResult({
        roles: ['placement_admin'],
        prn: null,
        email: 'pilot.officer@college.edu',
        full_name: 'Anika Verma',
      }),
      /all users/i,
      '/admin/users',
    ],
    [
      'Acme Tech recruiter',
      makeAuthResult({
        roles: ['company_recruiter:c-1'],
        prn: null,
        email: 'recruiter@acmetech.example',
        full_name: 'Priya Raman',
      }),
      null,
      '/company',
    ],
  ])(
    'after a redirect from an admin page, %s lands where that role may go',
    async (label, result, landmark, expectedPath) => {
      const user = userEvent.setup()
      mockApi([
        HEALTHY,
        { path: '/api/auth/demo/personas', body: PERSONAS },
        { path: '/api/auth/demo/login', method: 'POST', body: result },
        { path: '/api/auth/me', body: result.user },
        { path: '/api/auth/admin/users/summary', body: { total: 0, by_role: { student: 0, admin: 0, company: 0 }, by_status: {}, schools: [], batches: [] } },
        { path: '/api/auth/admin/users', body: { count: 0, next: null, previous: null, results: [] } },
      ])
      // Signed out on an admin page: the guard sends us to /login with `from`.
      renderApp('/admin/users')
      await user.click(
        await screen.findByRole('button', { name: new RegExp(`sign in as ${label}`, 'i') }),
      )

      // The nav marks the current page; only the landing area's nav is shown.
      await waitFor(() =>
        expect(screen.getByRole('button', { name: /sign out/i })).toBeInTheDocument(),
      )
      if (landmark) await waitFor(() => expect(screen.getAllByText(landmark).length).toBeGreaterThan(0))
      const active = document.querySelector('nav a[aria-current="page"]')
      expect(active?.getAttribute('href')).toBe(expectedPath)
    },
  )

  it('shows the server message if the persona is refused', async () => {
    const user = userEvent.setup()
    mockApi([
      HEALTHY,
      { path: '/api/auth/demo/personas', body: PERSONAS },
      { path: '/api/auth/demo/login', status: 404, body: { detail: 'No such demo persona.' } },
    ])
    renderApp('/login')

    await user.click(await screen.findByRole('button', { name: /sign in as student/i }))
    expect(await screen.findByText('No such demo persona.')).toBeInTheDocument()
  })
})
