import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import type { DirectorySummary, DirectoryUser } from '@/api/users'
import { HEALTHY, makeUser, mockApi, renderApp, type Route } from '@/test/harness'

const ADMIN = makeUser({
  roles: ['placement_admin'],
  prn: null,
  email: 'pilot.officer@college.edu',
  full_name: 'Anika Verma',
})

const STUDENT_ID = '3f2a1c9e-7b4d-4e2a-9c1f-5d8e6a0b1c2d'

function row(overrides: Partial<DirectoryUser>): DirectoryUser {
  return {
    id: 'u-1',
    full_name: 'Aarav Mehta',
    display_name: 'Aarav Mehta',
    email: 'aarav.mehta@college.edu',
    role: 'student',
    human_key: '220200901',
    prn: '220200901',
    admin_id: null,
    company: null,
    status: 'active',
    status_display: 'Currently enrolled',
    is_active: true,
    is_verified: true,
    profile_verified: true,
    onboarding_completed: true,
    student_id: STUDENT_ID,
    school: 'computing_data_science',
    school_name: 'School of Computing and Data Science',
    batch: 2026,
    last_login: '2026-11-15T09:30:00Z',
    date_joined: '2026-09-01T00:00:00Z',
    ...overrides,
  }
}

const STUDENT = row({})
const OFFICER = row({
  id: 'u-2',
  full_name: 'Anika Verma',
  display_name: 'Anika Verma',
  email: 'pilot.officer@college.edu',
  role: 'admin',
  human_key: 'ADM-0002',
  prn: null,
  admin_id: 'ADM-0002',
  is_verified: null,
  profile_verified: null,
  onboarding_completed: null,
  student_id: null,
  school: null,
  school_name: null,
  batch: null,
  last_login: null,
})
const RECRUITER = row({
  id: 'u-3',
  full_name: 'Priya Raman',
  display_name: 'Priya Raman',
  email: 'recruiter@acmetech.example',
  role: 'company',
  human_key: 'CMP-0001',
  prn: null,
  company: { id: 'c-1', company_id: 'CMP-0001', name: 'Acme Tech' },
  is_verified: null,
  profile_verified: null,
  onboarding_completed: null,
  student_id: null,
  school: null,
  school_name: null,
  batch: null,
})

const SUMMARY: DirectorySummary = {
  total: 7,
  by_role: { student: 4, admin: 2, company: 1 },
  by_status: {
    provisional: 0,
    active: 6,
    on_leave: 0,
    graduated: 1,
    withdrawn: 0,
    suspended: 0,
  },
  schools: [
    { key: 'computing_data_science', name: 'School of Computing and Data Science' },
    { key: 'business', name: 'School of Business' },
  ],
  batches: [2026, 2027],
}

function signedInAsAdmin(extra: Route[] = []) {
  localStorage.setItem('pcp.access', 'access-token')
  return mockApi([HEALTHY, { path: '/api/auth/me', body: ADMIN }, ...extra])
}

/** Every list request's query string, in order. */
function listQueries(fetchMock: ReturnType<typeof mockApi>): URLSearchParams[] {
  return fetchMock.mock.calls
    .map(([input]) => String(input))
    .filter((url) => url.startsWith('/api/auth/admin/users') && !url.includes('/summary'))
    .map((url) => new URLSearchParams(url.split('?')[1] ?? ''))
}

// The summary path is listed first: the harness matches by prefix, and the
// list path is a prefix of it.
const summaryRoute: Route = { path: '/api/auth/admin/users/summary', body: SUMMARY }

beforeEach(() => localStorage.clear())
afterEach(() => {
  vi.unstubAllGlobals()
  localStorage.clear()
})

describe('all users page', () => {
  it('shows every role with its human key, the role counts and the columns', async () => {
    signedInAsAdmin([
      summaryRoute,
      {
        path: '/api/auth/admin/users',
        body: { count: 3, next: null, previous: null, results: [STUDENT, OFFICER, RECRUITER] },
      },
    ])
    renderApp('/admin/users')

    await waitFor(() => expect(screen.getByText('ADM-0002')).toBeInTheDocument())
    expect(screen.getByRole('heading', { name: 'All users' })).toBeInTheDocument()

    const table = screen.getByRole('table')
    for (const header of ['Name', 'Role', 'Key', 'Email', 'Status', 'Verified', 'Onboarding', 'Last sign-in']) {
      expect(within(table).getByRole('columnheader', { name: header })).toBeInTheDocument()
    }
    expect(within(table).getByText('220200901')).toBeInTheDocument()
    expect(within(table).getByText('CMP-0001')).toBeInTheDocument()
    expect(within(table).getByText('Never')).toBeInTheDocument()
    expect(screen.getByText('Showing 1–3 of 3 accounts')).toBeInTheDocument()

    // Role counts across the top.
    const recruiters = screen.getByRole('button', { name: /recruiters/i })
    expect(within(recruiters).getByText('1')).toBeInTheDocument()
    expect(within(screen.getByRole('button', { name: /^4 students/i })).getByText('4')).toBeInTheDocument()
    expect(screen.getByText('All accounts').previousSibling).toHaveTextContent('7')
  })

  it('links a student to their profile and a recruiter to their company', async () => {
    const user = userEvent.setup()
    const fetchMock = signedInAsAdmin([
      summaryRoute,
      {
        path: '/api/auth/admin/users',
        body: { count: 2, next: null, previous: null, results: [STUDENT, RECRUITER] },
      },
    ])
    renderApp('/admin/users')

    const studentLink = await screen.findByRole('link', { name: 'Aarav Mehta' })
    expect(studentLink).toHaveAttribute('href', `/admin/profiles/${STUDENT_ID}`)
    // Only students link out; an officer or a recruiter has no profile page.
    expect(screen.queryByRole('link', { name: 'Priya Raman' })).not.toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Acme Tech' }))
    await waitFor(() => expect(listQueries(fetchMock).at(-1)?.get('company_id')).toBe('CMP-0001'))
    expect(screen.getByText(/showing the recruiters at/i)).toHaveTextContent('Acme Tech')
  })

  it.each([
    ['changing a filter', async (user: ReturnType<typeof userEvent.setup>) => {
      await user.selectOptions(screen.getByLabelText('Role'), 'student')
    }],
    ['clicking a role card', async (user: ReturnType<typeof userEvent.setup>) => {
      await user.click(screen.getByRole('button', { name: /recruiters/i }))
    }],
    ['searching', async (user: ReturnType<typeof userEvent.setup>) => {
      await user.type(screen.getByLabelText('Search'), 'rhea')
      await user.click(screen.getByRole('button', { name: 'Search' }))
    }],
    ['drilling into a company', async (user: ReturnType<typeof userEvent.setup>) => {
      await user.click(screen.getByRole('button', { name: 'Acme Tech' }))
    }],
    ['clearing the filters', async (user: ReturnType<typeof userEvent.setup>) => {
      await user.click(screen.getByRole('button', { name: 'Clear filters' }))
    }],
  ])('goes back to page one after %s', async (_label, act) => {
    const user = userEvent.setup()
    const fetchMock = signedInAsAdmin([
      summaryRoute,
      {
        path: '/api/auth/admin/users',
        body: {
          count: 45,
          next: '/api/auth/admin/users?page=2',
          previous: null,
          results: [STUDENT, RECRUITER],
        },
      },
    ])
    renderApp('/admin/users')
    await screen.findByText('Showing 1–20 of 45 accounts')

    // "Clear filters" only shows once something is filtered; set one first.
    if (_label === 'clearing the filters') {
      await user.selectOptions(screen.getByLabelText('Status'), 'active')
      await screen.findByRole('button', { name: 'Clear filters' })
    }

    await user.click(screen.getByRole('button', { name: 'Next' }))
    await waitFor(() => expect(listQueries(fetchMock).at(-1)?.get('page')).toBe('2'))
    await screen.findByText('Showing 21–40 of 45 accounts')
    const before = listQueries(fetchMock).length

    await act(user)

    await waitFor(() => expect(listQueries(fetchMock).length).toBeGreaterThan(before))
    expect(listQueries(fetchMock).at(-1)?.get('page')).toBe('1')
    expect(await screen.findByText('Showing 1–20 of 45 accounts')).toBeInTheDocument()
  })

  it('sends role, status, school, batch and search to the server', async () => {
    const user = userEvent.setup()
    const fetchMock = signedInAsAdmin([
      summaryRoute,
      {
        path: '/api/auth/admin/users',
        body: { count: 1, next: null, previous: null, results: [STUDENT] },
      },
    ])
    renderApp('/admin/users')
    await screen.findByText('220200901')
    // The summary fills the school and batch options.
    await screen.findByRole('option', { name: 'School of Business' })
    // One option per batch and per school, straight from the summary.
    expect(
      within(screen.getByLabelText('Batch')).getAllByRole('option').map((o) => o.textContent),
    ).toEqual(['All batches', '2026', '2027'])
    expect(within(screen.getByLabelText('School')).getAllByRole('option')).toHaveLength(3)

    await user.selectOptions(screen.getByLabelText('Role'), 'student')
    await user.selectOptions(screen.getByLabelText('Status'), 'active')
    await user.selectOptions(screen.getByLabelText('School'), 'business')
    await user.selectOptions(screen.getByLabelText('Batch'), '2027')
    await user.type(screen.getByLabelText('Search'), 'rhea')
    await user.click(screen.getByRole('button', { name: 'Search' }))

    await waitFor(() => expect(listQueries(fetchMock).at(-1)?.get('search')).toBe('rhea'))
    const last = listQueries(fetchMock).at(-1)!
    expect(last.get('role')).toBe('student')
    expect(last.get('status')).toBe('active')
    expect(last.get('school')).toBe('business')
    expect(last.get('batch')).toBe('2027')
  })

  it('shows only the latest request when responses come back out of order', async () => {
    const user = userEvent.setup()
    localStorage.setItem('pcp.access', 'access-token')
    const pending = new Map<string, (body: unknown) => void>()
    const respond = (body: unknown, status = 200) =>
      ({
        ok: status < 300,
        status,
        headers: new Headers(),
        text: async () => JSON.stringify(body),
      }) as Response
    vi.stubGlobal(
      'fetch',
      vi.fn(async (input: RequestInfo | URL) => {
        const url = String(input)
        if (url.startsWith('/api/health')) return respond(HEALTHY.body)
        if (url.startsWith('/api/auth/me')) return respond(ADMIN)
        if (url.startsWith('/api/auth/admin/users/summary')) return respond(SUMMARY)
        if (url.startsWith('/api/auth/admin/users')) {
          const role = new URLSearchParams(url.split('?')[1] ?? '').get('role') ?? 'all'
          // Hold the filtered requests so the test decides the order they land in.
          if (role === 'all') return respond({ count: 1, next: null, previous: null, results: [STUDENT] })
          return new Promise<Response>((resolve) =>
            pending.set(role, (body) => resolve(respond(body))),
          )
        }
        return respond({ detail: 'No mock' }, 404)
      }),
    )
    renderApp('/admin/users')
    await screen.findByText('220200901')

    await user.selectOptions(screen.getByLabelText('Role'), 'company')
    await user.selectOptions(screen.getByLabelText('Role'), 'admin')
    await waitFor(() => expect([...pending.keys()].sort()).toEqual(['admin', 'company']))

    // The later request (admin) answers first; the earlier one (company) answers late.
    pending.get('admin')!({ count: 1, next: null, previous: null, results: [OFFICER] })
    await screen.findByText('ADM-0002')
    pending.get('company')!({ count: 1, next: null, previous: null, results: [RECRUITER] })

    // Give the stale response every chance to render, then check it did not.
    await new Promise((resolve) => setTimeout(resolve, 50))
    expect(screen.getByText('ADM-0002')).toBeInTheDocument()
    expect(screen.queryByText('CMP-0001')).not.toBeInTheDocument()
    expect(screen.getByText('Showing 1–1 of 1 account')).toBeInTheDocument()
  })

  it('clears the previous rows when a reload fails', async () => {
    const user = userEvent.setup()
    let fail = false
    signedInAsAdmin([
      summaryRoute,
      {
        path: '/api/auth/admin/users',
        get status() {
          return fail ? 500 : 200
        },
        get body() {
          return fail
            ? { detail: 'Server error.' }
            : { count: 45, next: '/api/auth/admin/users?page=2', previous: null, results: [STUDENT] }
        },
      } as Route,
    ])
    renderApp('/admin/users')
    await screen.findByText('Showing 1–20 of 45 accounts')

    fail = true
    await user.click(screen.getByRole('button', { name: 'Next' }))

    expect(await screen.findByText('Server error.')).toBeInTheDocument()
    expect(screen.queryByText(/Showing \d+–\d+ of/)).not.toBeInTheDocument()
    expect(screen.queryByText('220200901')).not.toBeInTheDocument()
    expect(screen.queryByRole('table')).not.toBeInTheDocument()
  })

  it('pages through the results', async () => {
    const user = userEvent.setup()
    const fetchMock = signedInAsAdmin([
      summaryRoute,
      {
        path: '/api/auth/admin/users',
        body: {
          count: 45,
          next: '/api/auth/admin/users?page=2',
          previous: null,
          results: [STUDENT],
        },
      },
    ])
    renderApp('/admin/users')
    await screen.findByText('Showing 1–20 of 45 accounts')
    expect(screen.getByRole('button', { name: 'Previous' })).toBeDisabled()

    await user.click(screen.getByRole('button', { name: 'Next' }))
    await waitFor(() => expect(listQueries(fetchMock).at(-1)?.get('page')).toBe('2'))
    expect(await screen.findByText('Showing 21–40 of 45 accounts')).toBeInTheDocument()
  })

  it('surfaces a server refusal as a plain message', async () => {
    signedInAsAdmin([
      summaryRoute,
      { path: '/api/auth/admin/users', status: 403, body: { detail: 'Only placement cell admins can do this.' } },
    ])
    renderApp('/admin/users')
    expect(await screen.findByText('Only placement cell admins can do this.')).toBeInTheDocument()
  })

  it('is in the admin nav and on the admin home page', async () => {
    signedInAsAdmin([
      summaryRoute,
      { path: '/api/roster/students', body: { count: 0, results: [] } },
      { path: '/api/roster/flagged', body: { count: 0, results: [] } },
    ])
    renderApp('/admin')

    await waitFor(() => expect(screen.getByText('4 students · 2 admins · 1 recruiters')).toBeInTheDocument())
    expect(screen.getByRole('link', { name: 'All users' })).toHaveAttribute('href', '/admin/users')
    expect(screen.getByRole('link', { name: /every account/i })).toHaveAttribute('href', '/admin/users')
  })
})
