import { render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { fetchAll, pathOf } from '@/api/paginate'
import TruncationNote from '@/components/TruncationNote'
import { makeUser, mockApi, renderApp } from '@/test/harness'
import {
  COMPANY_USER,
  makeCompanyApplication,
  makeFeedRow,
  makeNotification,
  OPP_ID,
  signedInAs,
} from '@/test/opportunity-fixtures'

// The backend gives absolute `next` URLs on its own origin.
const ORIGIN = 'http://backend.internal:8000'

function twoPages<T>(path: string, first: T[], second: T[], total = first.length + second.length) {
  const secondPath = `${path}${path.includes('?') ? '&' : '?'}page=2`
  return [
    {
      // Page 2 first: its path also starts with page 1's.
      path: secondPath,
      body: { count: total, next: null, previous: `${ORIGIN}${path}`, results: second },
    },
    {
      path,
      body: { count: total, next: `${ORIGIN}${secondPath}`, previous: null, results: first },
    },
  ]
}

beforeEach(() => localStorage.clear())
afterEach(() => {
  vi.unstubAllGlobals()
  localStorage.clear()
})

describe('following pagination', () => {
  it('keeps only the path and query of an absolute next URL', () => {
    expect(pathOf('http://backend.internal:8000/api/x/?a=1&page=2')).toBe('/api/x/?a=1&page=2')
  })

  it('reads every page, and never calls the backend origin', async () => {
    const fetchMock = mockApi(twoPages('/api/things', [{ n: 1 }, { n: 2 }], [{ n: 3 }]))
    const got = await fetchAll<{ n: number }>('/api/things')
    expect(got.rows.map((r) => r.n)).toEqual([1, 2, 3])
    expect(got.count).toBe(3)
    expect(got.truncated).toBe(false)
    expect(fetchMock.mock.calls.map((c) => String(c[0]))).toEqual([
      '/api/things',
      '/api/things?page=2',
    ])
  })

  it('stops at the bound and says it was cut, with the server total', async () => {
    mockApi(twoPages('/api/things', [{ n: 1 }], [{ n: 2 }], 40))
    const got = await fetchAll<{ n: number }>('/api/things', 1)
    expect(got.rows).toHaveLength(1)
    expect(got.truncated).toBe(true)
    expect(got.count).toBe(40)

    render(<TruncationNote collected={got} />)
    expect(screen.getByText(/Showing the first 1 of 40/)).toBeInTheDocument()
  })

  it('renders nothing when everything arrived', () => {
    const { container } = render(
      <TruncationNote collected={{ rows: [1], count: 1, truncated: false }} />,
    )
    expect(container).toBeEmptyDOMElement()
  })
})

describe('pages show rows from every page', () => {
  it('applicants: page 2 rows are in the table', async () => {
    signedInAs(
      COMPANY_USER,
      twoPages(
        `/api/opportunities/applications?opportunity=${OPP_ID}`,
        [makeCompanyApplication({ id: 'a1', full_name: 'First Page', prn: '1' })],
        [makeCompanyApplication({ id: 'a2', full_name: 'Second Page', prn: '2' })],
      ),
    )
    renderApp(`/company/opportunities/${OPP_ID}/applicants`)

    expect(await screen.findByText('First Page')).toBeInTheDocument()
    expect(await screen.findByText('Second Page')).toBeInTheDocument()
    expect(screen.queryByText(/Showing the first/)).not.toBeInTheDocument()
  })

  it('jobs feed: page 2 postings are on the board', async () => {
    signedInAs(makeUser(), [
      { path: '/api/notifications/', body: { count: 0, next: null, previous: null, results: [] } },
      ...twoPages(
        '/api/opportunities/feed',
        [makeFeedRow({ id: 'f1', title: 'Job on page one' })],
        [makeFeedRow({ id: 'f2', title: 'Job on page two' })],
      ),
    ])
    renderApp('/student/jobs')

    expect(await screen.findByText('Job on page one')).toBeInTheDocument()
    expect(await screen.findByText('Job on page two')).toBeInTheDocument()
  })

  it('nav badge shows the server count, not the length of one page', async () => {
    signedInAs(makeUser(), [
      {
        path: '/api/notifications/?unread=true',
        body: {
          count: 37,
          next: `${ORIGIN}/api/notifications/?unread=true&page=2`,
          previous: null,
          results: [makeNotification()],
        },
      },
      { path: '/api/opportunities/applications', body: { count: 0, next: null, previous: null, results: [] } },
    ])
    renderApp('/student/applications')

    expect(await screen.findByText('37 unread')).toBeInTheDocument()
  })

  it('shortlist: the count text is the server count', async () => {
    const { makeCompanyProfile } = await import('@/test/fixtures')
    signedInAs(COMPANY_USER, [
      {
        path: '/api/profiles/students?shortlisted=true',
        body: { count: 45, next: null, previous: null, results: [makeCompanyProfile()] },
      },
    ])
    renderApp('/company/shortlist')

    expect(await screen.findByText('45 students on your shortlist')).toBeInTheDocument()
  })
})
