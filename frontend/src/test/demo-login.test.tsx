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
