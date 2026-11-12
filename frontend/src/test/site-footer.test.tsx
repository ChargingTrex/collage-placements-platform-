import '@testing-library/jest-dom/vitest'
import { screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { HEALTHY, makeUser, mockApi, renderApp } from '@/test/harness'

const ISSUES_URL = 'https://github.com/ChargingTrex/collage-placements-platform-/issues/new'

const STUDENT = makeUser()
const ADMIN = makeUser({
  roles: ['placement_admin'],
  prn: null,
  email: 'placement.officer@college.edu',
  full_name: 'Priya Kulkarni',
})

beforeEach(() => localStorage.clear())
afterEach(() => {
  vi.unstubAllGlobals()
  localStorage.clear()
})

/** The footer is mounted at the app root, so each wrapper gets it once. */
describe('site footer', () => {
  it('is on the signed-out landing page', async () => {
    mockApi([HEALTHY])
    renderApp('/')

    const link = await screen.findByRole('link', { name: /Raise an issue/ })
    expect(link).toHaveAttribute('href', ISSUES_URL)
  })

  it('is on the login page, which uses a different layout', async () => {
    mockApi([HEALTHY])
    renderApp('/login')

    expect(await screen.findByRole('link', { name: /Raise an issue/ })).toBeInTheDocument()
  })

  it('is on a signed-in page inside the nav shell', async () => {
    localStorage.setItem('pcp.access', 'access-token')
    mockApi([HEALTHY, { path: '/api/auth/me', body: STUDENT }])
    renderApp('/student')

    expect(await screen.findByRole('link', { name: /Raise an issue/ })).toBeInTheDocument()
  })

  it('is on the 404 page', async () => {
    mockApi([HEALTHY])
    renderApp('/no/such/route')

    expect(await screen.findByRole('link', { name: /Raise an issue/ })).toBeInTheDocument()
  })

  it('appears once per page, not once per layout', async () => {
    localStorage.setItem('pcp.access', 'access-token')
    mockApi([
      HEALTHY,
      { path: '/api/auth/me', body: ADMIN },
      { path: '/api/profiles/admin/outcomes', status: 500, body: { detail: 'nope' } },
      { path: '/api/profiles/admin', status: 500, body: { detail: 'nope' } },
    ])
    renderApp('/admin/outcomes')

    await screen.findByRole('contentinfo')
    expect(screen.getAllByRole('link', { name: /Raise an issue/ })).toHaveLength(1)
  })

  it('opens in a new tab without handing the repo the referrer', async () => {
    mockApi([HEALTHY])
    renderApp('/')

    const link = await screen.findByRole('link', { name: /Raise an issue/ })
    expect(link).toHaveAttribute('target', '_blank')
    expect(link).toHaveAttribute('rel', expect.stringContaining('noreferrer'))
  })
})
