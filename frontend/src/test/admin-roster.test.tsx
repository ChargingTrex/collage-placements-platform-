import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { HEALTHY, makeUser, mockApi, renderApp, type Route } from '@/test/harness'

const ADMIN = makeUser({
  roles: ['placement_admin'],
  prn: null,
  email: 'placement.officer@college.edu',
  full_name: 'Priya Kulkarni',
})

const ROSTER_ROW = {
  id: 'r-1',
  prn: '220200901',
  email: 'aarav.mehta@college.edu',
  full_name: 'Aarav Mehta',
  department: 'Computer Engineering',
  batch: 2026,
  cgpa: '8.72',
  phone: '',
  is_placement_eligible: true,
  has_account: true,
  created_at: '2026-09-01T00:00:00Z',
}

function signedInAsAdmin(extra: Route[] = []) {
  localStorage.setItem('pcp.access', 'access-token')
  return mockApi([HEALTHY, { path: '/api/auth/me', body: ADMIN }, ...extra])
}

beforeEach(() => localStorage.clear())
afterEach(() => {
  vi.unstubAllGlobals()
  localStorage.clear()
})

describe('roster upload', () => {
  it('lists the roster and reports how many students are on it', async () => {
    signedInAsAdmin([
      { path: '/api/roster/students', body: { count: 1, results: [ROSTER_ROW] } },
    ])
    renderApp('/admin/roster')

    await waitFor(() => expect(screen.getByText('220200901')).toBeInTheDocument())
    expect(screen.getByText('1 student on the roster.')).toBeInTheDocument()
    expect(screen.getByText('Registered')).toBeInTheDocument()
  })

  it('defaults to validate-only so a first upload cannot surprise you', async () => {
    signedInAsAdmin([{ path: '/api/roster/students', body: { count: 0, results: [] } }])
    renderApp('/admin/roster')

    await waitFor(() => expect(screen.getByText(/no students yet/i)).toBeInTheDocument())
    expect(screen.getByRole('checkbox', { name: /validate only/i })).toBeChecked()
    expect(screen.getByRole('button', { name: /check file/i })).toBeInTheDocument()
  })

  it('shows rejected rows by line number while keeping the accepted ones', async () => {
    const user = userEvent.setup()
    signedInAsAdmin([
      { path: '/api/roster/students', body: { count: 0, results: [] } },
      {
        path: '/api/roster/upload',
        status: 207,
        body: {
          dry_run: true,
          created: 1,
          updated: 0,
          unchanged: 0,
          processed: 1,
          error_count: 2,
          errors: [
            { row: 3, prn: '', errors: { prn: ['This field is required.'] } },
            { row: 4, prn: '220200953', errors: { cgpa: ['Enter a number between 0 and 10.'] } },
          ],
        },
      },
    ])
    renderApp('/admin/roster')

    await waitFor(() => expect(screen.getByLabelText(/csv file/i)).toBeInTheDocument())
    await user.upload(
      screen.getByLabelText(/csv file/i),
      new File(['prn,email\n'], 'roster.csv', { type: 'text/csv' }),
    )
    await user.click(screen.getByRole('button', { name: /check file/i }))

    await waitFor(() => expect(screen.getByText(/1 row\(s\) would apply/i)).toBeInTheDocument())
    expect(screen.getByText(/2 row\(s\) were rejected/i)).toBeInTheDocument()
    expect(screen.getByText(/nothing was saved/i)).toBeInTheDocument()

    const errorTable = screen.getByText('Problem').closest('table')!
    expect(within(errorTable).getByText('3')).toBeInTheDocument()
    expect(within(errorTable).getByText('220200953')).toBeInTheDocument()
    expect(within(errorTable).getByText(/between 0 and 10/i)).toBeInTheDocument()
  })

  it('surfaces a whole-file rejection as a plain message', async () => {
    const user = userEvent.setup()
    signedInAsAdmin([
      { path: '/api/roster/students', body: { count: 0, results: [] } },
      {
        path: '/api/roster/upload',
        status: 400,
        body: { detail: 'Missing required column(s): prn.' },
      },
    ])
    renderApp('/admin/roster')

    await waitFor(() => expect(screen.getByLabelText(/csv file/i)).toBeInTheDocument())
    await user.upload(
      screen.getByLabelText(/csv file/i),
      new File(['name,marks\n'], 'wrong.csv', { type: 'text/csv' }),
    )
    await user.click(screen.getByRole('button', { name: /check file/i }))

    await waitFor(() =>
      expect(screen.getByText(/missing required column\(s\): prn/i)).toBeInTheDocument(),
    )
  })
})

describe('flagged signups', () => {
  const FLAG = {
    id: 'f-7',
    prn: '220200999',
    email: 'ghost@college.edu',
    reason: 'no_such_prn',
    reason_display: 'PRN not on the roster',
    attempts: 3,
    status: 'open' as const,
    admin_note: '',
    reviewed_by_email: null,
    reviewed_at: null,
    created_at: '2026-09-20T10:00:00Z',
    updated_at: '2026-09-20T10:05:00Z',
  }

  it('shows open flags with the reason and the retry count', async () => {
    signedInAsAdmin([{ path: '/api/roster/flagged', body: { count: 1, results: [FLAG] } }])
    renderApp('/admin/flagged')

    await waitFor(() => expect(screen.getByText('220200999')).toBeInTheDocument())
    expect(screen.getByText('PRN not on the roster')).toBeInTheDocument()
    expect(screen.getByText('3 attempts')).toBeInTheDocument()
  })

  it('records a resolution with the admin note', async () => {
    const user = userEvent.setup()
    const calls: Array<{ method: string; body: unknown }> = []
    signedInAsAdmin([
      {
        path: '/api/roster/flagged/f-7/review',
        body: { ...FLAG, status: 'resolved' },
        onCall: (call) => calls.push(call),
      },
      { path: '/api/roster/flagged', body: { count: 1, results: [FLAG] } },
    ])
    renderApp('/admin/flagged')

    await waitFor(() => expect(screen.getByText('220200999')).toBeInTheDocument())
    await user.type(screen.getByLabelText(/note for 220200999/i), 'Added to the roster.')
    await user.click(screen.getByRole('button', { name: /^resolve$/i }))

    await waitFor(() => expect(calls).toHaveLength(1))
    expect(calls[0].body).toEqual({ status: 'resolved', admin_note: 'Added to the roster.' })
  })

  it('tells the admin when nothing is waiting', async () => {
    signedInAsAdmin([{ path: '/api/roster/flagged', body: { count: 0, results: [] } }])
    renderApp('/admin/flagged')

    await waitFor(() => expect(screen.getByText(/nothing flagged/i)).toBeInTheDocument())
  })
})
