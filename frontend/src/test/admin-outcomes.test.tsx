import '@testing-library/jest-dom/vitest'
import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import type { AdminProfile, Outcomes } from '@/api/profiles'
import { makeOwnProfile } from '@/test/fixtures'
import { HEALTHY, makeUser, mockApi, renderApp, type Route } from '@/test/harness'

const ADMIN = makeUser({
  roles: ['placement_admin'],
  prn: null,
  email: 'placement.officer@college.edu',
  full_name: 'Priya Kulkarni',
})

const PATHS = [
  { value: 'placement', label: 'Placement / campus recruitment' },
  { value: 'higher_studies', label: 'Higher studies' },
  { value: 'undecided', label: 'Not decided yet' },
]

const OUTCOMES: Outcomes = {
  batch: null,
  paths: PATHS,
  rows: [
    {
      school: 'computing_data_science',
      school_name: 'School of Computing and Data Science',
      counts: { placement: 3, higher_studies: 1, undecided: 1 },
      total: 5,
    },
    {
      school: 'unassigned',
      school_name: 'Unassigned',
      counts: { placement: 0, higher_studies: 2, undecided: 0 },
      total: 2,
    },
  ],
  totals: { placement: 3, higher_studies: 3, undecided: 1 },
  grand_total: 7,
  also_attending_placements: 2,
  verified: 4,
}

function makeAdminRow(overrides: Partial<AdminProfile> = {}): AdminProfile {
  return {
    ...makeOwnProfile(),
    verification_checks: [],
    warning_count: 0,
    ...overrides,
  }
}

const PEOPLE = {
  count: 2,
  next: null,
  previous: null,
  results: [
    makeAdminRow({
      student_id: 'stu-1',
      career_path: 'placement',
      is_verified: true,
      student: {
        prn: '220200901',
        full_name: 'Aarav Mehta',
        email: 'aarav.mehta@college.edu',
        department: 'Computer Engineering',
        batch: 2026,
        cgpa: '8.72',
        school: 'School of Computing and Data Science',
      },
    }),
    makeAdminRow({
      student_id: 'stu-2',
      career_path: 'higher_studies',
      student: {
        prn: '220200902',
        full_name: 'Diya Sharma',
        email: 'diya.sharma@college.edu',
        department: 'Computer Engineering',
        batch: 2026,
        cgpa: '7.90',
        school: 'School of Computing and Data Science',
      },
    }),
  ],
}

/**
 * `extra` goes first so a test can override a route, and the bare
 * `/api/profiles/admin` people route goes last: it is a prefix of the
 * outcomes path, and the harness takes the first match.
 */
function signedInAsAdmin(extra: Route[] = []) {
  localStorage.setItem('pcp.access', 'access-token')
  return mockApi([
    HEALTHY,
    { path: '/api/auth/me', body: ADMIN },
    ...extra,
    { path: '/api/profiles/admin/outcomes', body: OUTCOMES },
    { path: '/api/profiles/admin', body: PEOPLE },
  ])
}

/** The cross-tab, named apart from the people table below it. */
const crossTab = () =>
  screen.findByRole('table', { name: 'Students by school and career path' })

const peopleUrls = (fetchMock: ReturnType<typeof mockApi>) =>
  fetchMock.mock.calls
    .map(([url]) => String(url))
    .filter((url) => url.startsWith('/api/profiles/admin?'))

beforeEach(() => {
  localStorage.clear()
  URL.createObjectURL = vi.fn(() => 'blob:csv')
  URL.revokeObjectURL = vi.fn()
})
afterEach(() => {
  vi.unstubAllGlobals()
  localStorage.clear()
})

describe('outcomes page', () => {
  it('renders the school by path table with row and column totals', async () => {
    signedInAsAdmin()
    renderApp('/admin/outcomes')

    const table = await crossTab()
    const computing = within(table).getByRole('row', { name: /School of Computing/ })
    expect(within(computing).getAllByRole('cell').map((cell) => cell.textContent)).toEqual([
      '3',
      '1',
      '1',
      '5',
    ])
    const total = within(table).getByRole('row', { name: /^Total/ })
    expect(within(total).getAllByRole('cell').map((cell) => cell.textContent)).toEqual([
      '3',
      '3',
      '1',
      '7',
    ])
    expect(screen.getByText('Also attending placements')).toBeInTheDocument()
  })

  it('filters by batch', async () => {
    const user = userEvent.setup()
    const urls: string[] = []
    const fetchMock = signedInAsAdmin()
    renderApp('/admin/outcomes')
    await crossTab()

    await user.type(screen.getByLabelText('Batch'), '2026')
    await user.click(screen.getByRole('button', { name: 'Apply' }))

    await waitFor(() => {
      urls.push(...fetchMock.mock.calls.map(([url]) => String(url)))
      expect(urls).toContain('/api/profiles/admin/outcomes?batch=2026')
    })
  })

  it('exports the CSV through the bearer fetch', async () => {
    const user = userEvent.setup()
    const auth: Array<string | null> = []
    signedInAsAdmin([
      {
        path: '/api/profiles/admin/outcomes/export',
        body: 'school,placement,total',
        onCall: ({ authorization }) => auth.push(authorization),
      },
    ])
    renderApp('/admin/outcomes')

    await user.click(await screen.findByRole('button', { name: 'Export CSV' }))

    await waitFor(() => expect(auth).toEqual(['Bearer access-token']))
    expect(URL.createObjectURL).toHaveBeenCalled()
  })

  it('shows an empty state with no students', async () => {
    signedInAsAdmin([
      {
        path: '/api/profiles/admin/outcomes',
        body: { ...OUTCOMES, rows: [], totals: {}, grand_total: 0 },
      },
    ])
    renderApp('/admin/outcomes')

    expect(await screen.findByText('No students counted')).toBeInTheDocument()
  })
})

describe('outcomes bars', () => {
  it('shows a bar per career path, biggest first, with its count and share', async () => {
    signedInAsAdmin()
    renderApp('/admin/outcomes')
    await crossTab()

    // Sorted by size, not by the enum order the server sends.
    const labels = screen
      .getAllByRole('button', { pressed: false })
      .map((button) => button.getAttribute('title'))
      .filter((title): title is string => Boolean(title))

    expect(labels).toContain('Placement / campus recruitment: 3 students (43% of 7)')
    expect(labels).toContain('Higher studies: 3 students (43% of 7)')
    expect(labels).toContain('Not decided yet: 1 student (14% of 7)')
    // The school chart counts against the same grand total.
    expect(labels).toContain('School of Computing and Data Science: 5 students (71% of 7)')
    expect(labels).toContain('Unassigned: 2 students (29% of 7)')
  })

  it('ranks the career path bars largest first', async () => {
    signedInAsAdmin()
    renderApp('/admin/outcomes')
    await crossTab()

    const titles = screen
      .getAllByRole('button')
      .map((button) => button.getAttribute('title') ?? '')
      .filter((title) => title.includes('student'))

    const undecided = titles.findIndex((title) => title.startsWith('Not decided yet'))
    const placement = titles.findIndex((title) => title.startsWith('Placement'))
    expect(placement).toBeLessThan(undecided)
  })

  it('clicking a career path bar narrows the people table to that path', async () => {
    const user = userEvent.setup()
    const fetchMock = signedInAsAdmin()
    renderApp('/admin/outcomes')
    await crossTab()

    await user.click(screen.getByTitle('Higher studies: 3 students (43% of 7)'))

    await waitFor(() =>
      expect(peopleUrls(fetchMock).some((url) => url.includes('career_path=higher_studies'))).toBe(
        true,
      ),
    )
    // And it says so, with a way back out.
    expect(await screen.findByRole('button', { name: /Higher studies ✕/ })).toBeInTheDocument()
  })

  it('clicking a school bar narrows the people table to that school', async () => {
    const user = userEvent.setup()
    const fetchMock = signedInAsAdmin()
    renderApp('/admin/outcomes')
    await crossTab()

    await user.click(
      screen.getByTitle('School of Computing and Data Science: 5 students (71% of 7)'),
    )

    await waitFor(() =>
      expect(
        peopleUrls(fetchMock).some((url) => url.includes('school=computing_data_science')),
      ).toBe(true),
    )
  })

  it('clicking the selected bar again clears the filter', async () => {
    const user = userEvent.setup()
    signedInAsAdmin()
    renderApp('/admin/outcomes')
    await crossTab()

    const bar = screen.getByTitle('Higher studies: 3 students (43% of 7)')
    await user.click(bar)
    expect(await screen.findByRole('button', { name: /Higher studies ✕/ })).toBeInTheDocument()

    await user.click(bar)
    await waitFor(() =>
      expect(screen.queryByRole('button', { name: /Higher studies ✕/ })).not.toBeInTheDocument(),
    )
  })
})

describe('outcomes people table', () => {
  it('lists the students behind the bars', async () => {
    signedInAsAdmin()
    renderApp('/admin/outcomes')

    const people = await screen.findByRole('table', {
      name: 'Students matching the current filters',
    })
    const aarav = within(people).getByRole('row', { name: /Aarav Mehta/ })
    expect(within(aarav).getByText('220200901')).toBeInTheDocument()
    expect(within(aarav).getByText('Placement / campus recruitment')).toBeInTheDocument()
    expect(within(aarav).getByText('8.72')).toBeInTheDocument()
    expect(within(people).getByRole('row', { name: /Diya Sharma/ })).toBeInTheDocument()
    expect(screen.getByText('2 students')).toBeInTheDocument()
  })

  it('links each student to their full profile', async () => {
    signedInAsAdmin()
    renderApp('/admin/outcomes')

    const link = await screen.findByRole('link', { name: 'Aarav Mehta' })
    expect(link).toHaveAttribute('href', '/admin/profiles/stu-1')
  })

  it('searches by name, PRN or email on submit', async () => {
    const user = userEvent.setup()
    const fetchMock = signedInAsAdmin()
    renderApp('/admin/outcomes')
    await crossTab()

    await user.type(screen.getByLabelText('Search'), 'Diya')
    await user.click(screen.getByRole('button', { name: 'Search' }))

    await waitFor(() =>
      expect(peopleUrls(fetchMock).some((url) => url.includes('search=Diya'))).toBe(true),
    )
  })

  it('does not fire a request a letter while typing', async () => {
    const user = userEvent.setup()
    const fetchMock = signedInAsAdmin()
    renderApp('/admin/outcomes')
    await crossTab()
    const before = peopleUrls(fetchMock).length

    await user.type(screen.getByLabelText('Search'), 'Diya')

    expect(peopleUrls(fetchMock).length).toBe(before)
  })

  it('carries the applied batch into the people query', async () => {
    const user = userEvent.setup()
    const fetchMock = signedInAsAdmin()
    renderApp('/admin/outcomes')
    await crossTab()

    await user.type(screen.getByLabelText('Batch'), '2026')
    await user.click(screen.getByRole('button', { name: 'Apply' }))

    await waitFor(() =>
      expect(peopleUrls(fetchMock).some((url) => url.includes('batch=2026'))).toBe(true),
    )
  })
})
