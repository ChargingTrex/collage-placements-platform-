import '@testing-library/jest-dom/vitest'
import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { makeCompanyProfile, makeOwnProfile } from '@/test/fixtures'
import { HEALTHY, makeUser, mockApi, renderApp, type Route } from '@/test/harness'
import {
  JOB_SUMMARY,
  LEAKED_FIELDS,
  makeAnalysis,
  makeMatchResult,
  makeMatchScore,
  RESUME_FACTS,
} from '@/test/intelligence-fixtures'

const COMPANY = makeUser({
  roles: ['company_recruiter:7a1b2c3d-0000-4000-8000-00000000c0de'],
  prn: null,
  email: 'recruiter@acmetech.example',
  full_name: 'Acme Tech',
})

const JD = 'Backend engineer: Python, Django and Docker, one year of experience building APIs.'
const SEARCH = '/api/matching/search'
const CATEGORIES = {
  path: '/api/matching/categories',
  body: {
    count: 2,
    next: null,
    previous: null,
    results: [
      { name: 'Backend Engineer', jd_count: 3, top_skills: ['Python', 'Django'] },
      { name: 'Data Analyst', jd_count: 1, top_skills: ['SQL'] },
    ],
  },
} satisfies Route
const EMPTY_PAGE = { count: 0, next: null, previous: null, results: [] }

const DIYA_ID = '9b1d2e3f-4a5b-4c6d-8e7f-0a1b2c3d4e5f'
const RANKED = [
  makeMatchResult({}, { score: 81 }),
  makeMatchResult(
    {
      id: 'p-2',
      student_id: DIYA_ID,
      prn: '220200922',
      student: { ...makeOwnProfile().student, prn: '220200922', full_name: 'Diya Shah' },
      headline: 'Data analyst',
    },
    { score: 44, matched_skills: ['Python'], missing_skills: ['Django', 'Docker'] },
  ),
]

function signedInAsCompany(extra: Route[] = []) {
  localStorage.setItem('pcp.access', 'access-token')
  return mockApi([HEALTHY, { path: '/api/auth/me', body: COMPANY }, ...extra])
}

async function rankAgainst(user: ReturnType<typeof userEvent.setup>, text = JD) {
  const box = await screen.findByLabelText('Job description')
  await user.click(box)
  await user.paste(text)
  await user.click(screen.getByRole('button', { name: 'Rank students' }))
}

beforeEach(() => localStorage.clear())
afterEach(() => {
  vi.unstubAllGlobals()
  localStorage.clear()
})

describe('company match against a job description', () => {
  it('ranks students with a score bar, skill chips and a breakdown on request', async () => {
    const user = userEvent.setup()
    const calls: Array<{ method: string; body: unknown }> = []
    signedInAsCompany([
      {
        path: SEARCH,
        method: 'POST',
        body: { count: 2, fallback: true, job: JOB_SUMMARY, results: RANKED },
        onCall: (call) => calls.push(call),
      },
      CATEGORIES,
      { path: '/api/profiles/students', body: EMPTY_PAGE },
    ])
    renderApp('/company/students')
    await rankAgainst(user)

    const ranked = await screen.findByRole('list', { name: 'Ranked students' })
    expect(calls[0].body).toEqual({ jd_text: JD, k: 20, filters: {} })
    expect(screen.getByText(/2 matches · read as Backend Engineer/)).toBeInTheDocument()

    const [first, second] = within(ranked).getAllByRole('listitem').filter((item) => item.parentElement === ranked)
    expect(within(first).getByRole('link', { name: 'Aarav Mehta' })).toHaveAttribute(
      'href',
      `/company/students/${RANKED[0].student_id}`,
    )
    expect(within(first).getByText('Match 81 of 100')).toBeInTheDocument()
    expect(within(second).getByRole('link', { name: 'Diya Shah' })).toHaveAttribute(
      'href',
      `/company/students/${DIYA_ID}`,
    )
    expect(within(second).getByText('Match 44 of 100')).toBeInTheDocument()
    expect(within(within(second).getByRole('list', { name: 'Missing skills' })).getByText('Django')).toBeInTheDocument()

    const toggle = within(first).getByRole('button', { name: 'Show score breakdown' })
    expect(toggle).toHaveAttribute('aria-expanded', 'false')
    expect(within(first).queryByRole('table', { name: 'Match breakdown' })).not.toBeInTheDocument()

    await user.click(toggle)
    expect(toggle).toHaveAttribute('aria-expanded', 'true')
    const breakdown = within(first).getByRole('table', { name: 'Match breakdown' })
    expect(within(within(breakdown).getByRole('row', { name: /^Semantic/ })).getByText('45%')).toBeInTheDocument()

    expect(document.body.textContent).not.toMatch(/probabilit/i)
  })

  it('says so when no visible student matches', async () => {
    const user = userEvent.setup()
    signedInAsCompany([
      { path: SEARCH, method: 'POST', body: { count: 0, fallback: false, job: JOB_SUMMARY, results: [] } },
      CATEGORIES,
      { path: '/api/profiles/students', body: EMPTY_PAGE },
    ])
    renderApp('/company/students')
    await rankAgainst(user)

    expect(await screen.findByText('No students match this job description')).toBeInTheDocument()
  })

  it('shows the server validation message against the job description', async () => {
    const user = userEvent.setup()
    signedInAsCompany([
      {
        path: SEARCH,
        method: 'POST',
        status: 400,
        body: { jd_text: ['Ensure this field has no more than 20000 characters.'] },
      },
      CATEGORIES,
      { path: '/api/profiles/students', body: EMPTY_PAGE },
    ])
    renderApp('/company/students')
    await rankAgainst(user)

    expect(
      await screen.findByText('Ensure this field has no more than 20000 characters.'),
    ).toBeInTheDocument()
    expect(screen.getByLabelText('Job description')).toHaveAttribute('aria-invalid', 'true')
  })

  it('reports a 400 on the filters as an error', async () => {
    const user = userEvent.setup()
    signedInAsCompany([
      {
        path: SEARCH,
        method: 'POST',
        status: 400,
        // The shape MatchFiltersField raises: a dict keyed by filter, not a list.
        body: {
          filters: {
            age: 'Unknown filter. Use one of: department, batch, education_level, experience_months, skills, categories.',
          },
        },
      },
      CATEGORIES,
      { path: '/api/profiles/students', body: EMPTY_PAGE },
    ])
    renderApp('/company/students')
    await rankAgainst(user)

    await waitFor(() =>
      expect(screen.getByRole('alert')).toHaveTextContent(
        'age: Unknown filter. Use one of: department, batch, education_level, experience_months, skills, categories.',
      ),
    )
    expect(screen.getByRole('alert')).not.toHaveTextContent('[object Object]')
  })

  it('announces the too-short job description as an alert tied to the field', async () => {
    const user = userEvent.setup()
    const searches: Array<{ method: string; body: unknown }> = []
    signedInAsCompany([
      { path: SEARCH, method: 'POST', body: {}, onCall: (call) => searches.push(call) },
      CATEGORIES,
      { path: '/api/profiles/students', body: EMPTY_PAGE },
    ])
    renderApp('/company/students')
    await rankAgainst(user, 'Python dev')

    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent('Paste at least 30 characters of the job description.')
    const box = screen.getByLabelText('Job description')
    expect(box).toHaveAttribute('aria-invalid', 'true')
    expect(box).toHaveAttribute('aria-describedby', alert.id)
    expect(searches).toHaveLength(0)
  })

  it('explains the hourly limit when the matcher answers 429', async () => {
    const user = userEvent.setup()
    signedInAsCompany([
      {
        path: SEARCH,
        method: 'POST',
        status: 429,
        body: { detail: 'Request was throttled. Expected available in 45 seconds.' },
      },
      CATEGORIES,
      { path: '/api/profiles/students', body: EMPTY_PAGE },
    ])
    renderApp('/company/students')
    await rankAgainst(user)

    await waitFor(() =>
      expect(screen.getByRole('alert')).toHaveTextContent(
        'You have run the matcher too many times in the last hour. Try again in about 1 minute.',
      ),
    )
  })

  it('never renders age, date of birth or the resume CGPA in a ranked result', async () => {
    const user = userEvent.setup()
    signedInAsCompany([
      {
        path: SEARCH,
        method: 'POST',
        body: {
          count: 1,
          fallback: false,
          job: JOB_SUMMARY,
          results: [{ ...makeMatchResult(), ...LEAKED_FIELDS, analysis: makeAnalysis() }],
        },
      },
      CATEGORIES,
      { path: '/api/profiles/students', body: { ...EMPTY_PAGE, results: [{ ...makeCompanyProfile(), ...LEAKED_FIELDS }], count: 1 } },
    ])
    renderApp('/company/students')
    await rankAgainst(user)

    await screen.findByRole('list', { name: 'Ranked students' })
    await user.click(screen.getByRole('button', { name: 'Show score breakdown' }))
    const page = document.body.textContent ?? ''
    expect(page).not.toContain(RESUME_FACTS.date_of_birth)
    expect(page).not.toContain(String(RESUME_FACTS.cgpa))
    expect(page).not.toMatch(/date of birth|\bage\b|warning/i)
    // The roster CGPA is the company's to see; the resume's is not.
    expect(page).toContain('8.72')
  })
})

describe('company role category filter', () => {
  it('offers the categories and applies the choice to the list and to the JD match', async () => {
    const user = userEvent.setup()
    const searches: Array<{ method: string; body: unknown }> = []
    const fetchMock = signedInAsCompany([
      {
        path: SEARCH,
        method: 'POST',
        body: { count: 1, fallback: false, job: JOB_SUMMARY, results: [makeMatchResult()] },
        onCall: (call) => searches.push(call),
      },
      CATEGORIES,
      { path: '/api/profiles/students', body: EMPTY_PAGE },
    ])
    renderApp('/company/students')

    const select = await screen.findByLabelText('Role category')
    await waitFor(() =>
      expect(within(select).getByRole('option', { name: 'Backend Engineer' })).toBeInTheDocument(),
    )
    await user.selectOptions(select, 'Backend Engineer')
    await user.click(screen.getByRole('button', { name: /apply/i }))

    await waitFor(() => {
      const urls = fetchMock.mock.calls.map(([url]) => String(url))
      expect(urls.some((url) => url.includes('category=Backend+Engineer'))).toBe(true)
    })

    await rankAgainst(user)
    await waitFor(() => expect(searches).toHaveLength(1))
    expect(searches[0].body).toEqual({ jd_text: JD, k: 20, filters: { categories: 'Backend Engineer' } })
    expect(screen.getByText('Backend Engineer', { selector: 'strong' })).toBeInTheDocument()
  })

  it('matches against the applied category, not one only chosen in the form', async () => {
    const user = userEvent.setup()
    const searches: Array<{ method: string; body: unknown }> = []
    signedInAsCompany([
      {
        path: SEARCH,
        method: 'POST',
        body: { count: 1, fallback: false, job: JOB_SUMMARY, results: [makeMatchResult()] },
        onCall: (call) => searches.push(call),
      },
      CATEGORIES,
      { path: '/api/profiles/students', body: EMPTY_PAGE },
    ])
    renderApp('/company/students')

    const select = await screen.findByLabelText('Role category')
    await waitFor(() =>
      expect(within(select).getByRole('option', { name: 'Data Analyst' })).toBeInTheDocument(),
    )
    // Chosen but not applied: the list still shows every category, and so must the match.
    await user.selectOptions(select, 'Data Analyst')
    expect(screen.queryByText(/^In category/)).not.toBeInTheDocument()

    await rankAgainst(user)
    await waitFor(() => expect(searches).toHaveLength(1))
    expect(searches[0].body).toEqual({ jd_text: JD, k: 20, filters: {} })

    await user.click(screen.getByRole('button', { name: /apply/i }))
    expect(await screen.findByText('Data Analyst', { selector: 'strong' })).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Rank students' }))
    await waitFor(() => expect(searches).toHaveLength(2))
    expect(searches[1].body).toEqual({ jd_text: JD, k: 20, filters: { categories: 'Data Analyst' } })

    await user.click(screen.getByRole('button', { name: 'Clear' }))
    await user.click(screen.getByRole('button', { name: 'Rank students' }))
    await waitFor(() => expect(searches).toHaveLength(3))
    expect(searches[2].body).toEqual({ jd_text: JD, k: 20, filters: {} })
  })

  it('offers every category, following the pages past the first twenty', async () => {
    const names = Array.from({ length: 21 }, (_, index) => `Role ${String(index + 1).padStart(2, '0')}`)
    const category = (name: string) => ({ name, jd_count: 1, top_skills: [] })
    const fetchMock = signedInAsCompany([
      {
        path: '/api/matching/categories?page=2',
        body: {
          count: 21,
          next: null,
          previous: 'http://testserver/api/matching/categories',
          results: names.slice(20).map(category),
        },
      },
      {
        path: '/api/matching/categories',
        body: {
          count: 21,
          next: 'http://testserver/api/matching/categories?page=2',
          previous: null,
          results: names.slice(0, 20).map(category),
        },
      },
      { path: '/api/profiles/students', body: EMPTY_PAGE },
    ])
    renderApp('/company/students')

    const select = await screen.findByLabelText('Role category')
    await waitFor(() =>
      expect(within(select).getByRole('option', { name: 'Role 21' })).toBeInTheDocument(),
    )
    // "Any", then all 21.
    expect(within(select).getAllByRole('option')).toHaveLength(22)
    const pages = fetchMock.mock.calls.map(([url]) => String(url)).filter((url) => url.includes('/api/matching/categories'))
    // Same origin as the page: the server's absolute `next` is followed by its path.
    expect(pages).toEqual(['/api/matching/categories', '/api/matching/categories?page=2'])
  })

  it('stops following category pages after ten', async () => {
    const fetchMock = signedInAsCompany([
      {
        path: '/api/matching/categories',
        body: {
          count: 999,
          next: 'http://testserver/api/matching/categories?page=2',
          previous: null,
          results: [{ name: 'Backend Engineer', jd_count: 1, top_skills: [] }],
        },
      },
      { path: '/api/profiles/students', body: EMPTY_PAGE },
    ])
    renderApp('/company/students')

    const select = await screen.findByLabelText('Role category')
    await waitFor(() =>
      expect(within(select).getByRole('option', { name: 'Backend Engineer' })).toBeInTheDocument(),
    )
    const pages = () =>
      fetchMock.mock.calls.filter(([url]) => String(url).includes('/api/matching/categories'))
    await waitFor(() => expect(pages()).toHaveLength(10))
    await new Promise((resolve) => setTimeout(resolve, 50))
    expect(pages()).toHaveLength(10)
  })

  it('says there are no categories yet when recruiters have posted none', async () => {
    signedInAsCompany([
      { path: '/api/matching/categories', body: EMPTY_PAGE },
      { path: '/api/profiles/students', body: EMPTY_PAGE },
    ])
    renderApp('/company/students')

    expect(
      await screen.findByText('No categories yet: they appear as recruiters post job descriptions.'),
    ).toBeInTheDocument()
    const select = screen.getByLabelText('Role category')
    expect(within(select).getAllByRole('option')).toHaveLength(1)
  })
})

describe('score breakdown wording', () => {
  it('shows the flagged badge when a hard requirement is not met', async () => {
    const user = userEvent.setup()
    signedInAsCompany([
      {
        path: SEARCH,
        method: 'POST',
        body: {
          count: 1,
          fallback: false,
          job: { ...JOB_SUMMARY, min_experience_years: 2 },
          results: [
            makeMatchResult(
              {},
              makeMatchScore({
                flagged: true,
                // The wording MatchingEngine._hard_filter_failure gives.
                hard_filter_failures: ['Needs 2 years of experience; resume shows 1.8.'],
              }),
            ),
          ],
        },
      },
      CATEGORIES,
      { path: '/api/profiles/students', body: EMPTY_PAGE },
    ])
    renderApp('/company/students')
    await rankAgainst(user)

    expect(await screen.findByText('Below a requirement')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Show score breakdown' }))
    expect(screen.getByText('Needs 2 years of experience; resume shows 1.8.')).toBeVisible()
  })
})
