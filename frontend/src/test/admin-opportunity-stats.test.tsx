import { screen, within } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { renderApp } from '@/test/harness'
import { ADMIN_USER, signedInAs } from '@/test/opportunity-fixtures'

beforeEach(() => localStorage.clear())
afterEach(() => {
  vi.unstubAllGlobals()
  localStorage.clear()
})

describe('admin opportunity figures', () => {
  it('shows counts, the median and the per-posting table', async () => {
    signedInAs(ADMIN_USER, [
      {
        path: '/api/opportunities/stats',
        body: {
          opportunities_by_status: { open: 3, pending_review: 1 },
          applications_by_status: { applied: 5, shortlisted: 2 },
          per_opportunity: [
            { id: 'x', title: 'Backend Engineer', company: 'Acme Tech', applicants: 7, by_status: { applied: 5, shortlisted: 2 } },
          ],
          median_hours_to_shortlist: 26.5,
        },
      },
    ])
    renderApp('/admin/opportunities/stats')

    expect(await screen.findByText('26.5 hours')).toBeInTheDocument()
    const posting = within(screen.getByText('Backend Engineer').closest('tr')!)
    expect(posting.getByText('7')).toBeInTheDocument()
    expect(posting.getByText('applied 5, shortlisted 2')).toBeInTheDocument()
    expect(screen.getByText('pending review')).toBeInTheDocument()
  })

  it('says so when nobody has been shortlisted', async () => {
    signedInAs(ADMIN_USER, [
      {
        path: '/api/opportunities/stats',
        body: {
          opportunities_by_status: {},
          applications_by_status: {},
          per_opportunity: [],
          median_hours_to_shortlist: null,
        },
      },
    ])
    renderApp('/admin/opportunities/stats')
    expect(await screen.findByText(/no application has been shortlisted yet/i)).toBeInTheDocument()
  })
})
