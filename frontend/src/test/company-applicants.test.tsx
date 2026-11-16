import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { renderApp } from '@/test/harness'
import {
  COMPANY_USER,
  makeCompanyApplication,
  OPP_ID,
  page,
  signedInAs,
} from '@/test/opportunity-fixtures'

const PAGE = `/company/opportunities/${OPP_ID}/applicants`
const API = `/api/opportunities/${OPP_ID}`

beforeEach(() => {
  localStorage.clear()
  URL_STUB()
})
afterEach(() => {
  vi.unstubAllGlobals()
  localStorage.clear()
})

function URL_STUB() {
  globalThis.URL.createObjectURL = vi.fn(() => 'blob:csv')
  globalThis.URL.revokeObjectURL = vi.fn()
}

function row(text: string) {
  return within(screen.getByText(text).closest('tr')!)
}

describe('company applicants', () => {
  it('shows eligibility apart from the score and hides contact when unavailable', async () => {
    signedInAs(COMPANY_USER, [
      {
        path: '/api/opportunities/applications',
        body: page([
          makeCompanyApplication(),
          makeCompanyApplication({
            id: 'app-2',
            prn: '220200902',
            full_name: 'Diya Rao',
            eligible: false,
            eligibility_reasons: ['Department is not on the posting’s list.'],
            contact: { email: 'diya@example.com', phone: '9000000000' },
            contact_available: true,
          }),
        ]),
      },
    ])
    renderApp(PAGE)

    await screen.findByText('Aarav Mehta')
    const aarav = row('Aarav Mehta')
    expect(aarav.getByText('Match 81 of 100')).toBeInTheDocument()
    expect(aarav.getByText('Eligible')).toBeInTheDocument()
    expect(aarav.queryByText(/@/)).not.toBeInTheDocument()

    const diya = row('Diya Rao')
    expect(diya.getByText('Not eligible')).toBeInTheDocument()
    expect(diya.getByText(/department is not on the posting/i)).toBeInTheDocument()
    expect(diya.getByText(/diya@example\.com/)).toBeInTheDocument()

    const text = document.body.textContent?.toLowerCase() ?? ''
    for (const banned of ['probability', 'marksheet', 'transcript', 'career path']) {
      expect(text).not.toContain(banned)
    }
  })

  it('offers only the allowed status moves and sends the chosen one', async () => {
    const user = userEvent.setup()
    let sent: unknown
    signedInAs(COMPANY_USER, [
      {
        path: '/api/opportunities/applications/app-1/status',
        method: 'POST',
        body: makeCompanyApplication({ status: 'shortlisted' }),
        onCall: ({ body }) => {
          sent = body
        },
      },
      { path: '/api/opportunities/applications', body: page([makeCompanyApplication()]) },
    ])
    renderApp(PAGE)
    await screen.findByText('Aarav Mehta')

    const select = screen.getByLabelText('Move Aarav Mehta to')
    expect(within(select).getAllByRole('option').map((o) => o.textContent)).toEqual([
      'Move to…',
      'Shortlisted',
      'Rejected',
    ])
    await user.selectOptions(select, 'shortlisted')
    await user.click(screen.getByRole('button', { name: 'Move' }))

    await waitFor(() => expect(sent).toEqual({ status: 'shortlisted' }))
    // Now shortlisted: the next legal moves are interview or rejected.
    await waitFor(() =>
      expect(
        within(screen.getByLabelText('Move Aarav Mehta to'))
          .getAllByRole('option')
          .map((o) => o.textContent),
      ).toEqual(['Move to…', 'Interview', 'Rejected']),
    )
  })

  it('offers no move from a final status', async () => {
    signedInAs(COMPANY_USER, [
      {
        path: '/api/opportunities/applications',
        body: page([makeCompanyApplication({ status: 'offer' })]),
      },
    ])
    renderApp(PAGE)
    await screen.findByText('Aarav Mehta')
    expect(screen.getByText('No further moves')).toBeInTheDocument()
    expect(screen.queryByLabelText('Move Aarav Mehta to')).not.toBeInTheDocument()
  })

  it('shows a refused move in place', async () => {
    const user = userEvent.setup()
    signedInAs(COMPANY_USER, [
      {
        path: '/api/opportunities/applications/app-1/status',
        method: 'POST',
        status: 400,
        body: { detail: 'That move is not allowed.' },
      },
      { path: '/api/opportunities/applications', body: page([makeCompanyApplication()]) },
    ])
    renderApp(PAGE)
    await screen.findByText('Aarav Mehta')

    await user.selectOptions(screen.getByLabelText('Move Aarav Mehta to'), 'rejected')
    await user.click(screen.getByRole('button', { name: 'Move' }))

    expect(await screen.findByText('That move is not allowed.')).toBeInTheDocument()
  })

  it('exports the CSV through the authenticated download', async () => {
    const user = userEvent.setup()
    const fetchMock = signedInAs(COMPANY_USER, [
      {
        path: `${API}/applicants/export`,
        headers: { 'Content-Disposition': 'attachment; filename="applicants.csv"' },
        body: 'prn,full_name',
      },
      { path: '/api/opportunities/applications', body: page([makeCompanyApplication()]) },
    ])
    renderApp(PAGE)
    await screen.findByText('Aarav Mehta')

    await user.click(screen.getByRole('button', { name: 'Export CSV' }))

    await waitFor(() => expect(globalThis.URL.createObjectURL).toHaveBeenCalled())
    const exportCall = fetchMock.mock.calls.find((call) => String(call[0]).endsWith('/applicants/export'))
    expect(new Headers(exportCall?.[1]?.headers).get('Authorization')).toBe('Bearer access-token')
  })

  it('screens applicants, sending only the filled fields, and shortlists the passers in bulk', async () => {
    const user = userEvent.setup()
    let screenBody: unknown
    const moved: string[] = []
    const passer = {
      application_id: 'app-1',
      prn: '220200901',
      full_name: 'Aarav Mehta',
      score: 81,
      experience_years: 2,
      education_levels: ['UG'],
      reasons: [],
    }
    signedInAs(COMPANY_USER, [
      {
        path: `${API}/screen`,
        method: 'POST',
        body: {
          shortlisted: [passer],
          below_threshold: [],
          filtered_out: [{ ...passer, application_id: 'app-9', full_name: 'Zed Low', reasons: ['Needs 3 years of experience.'] }],
        },
        onCall: ({ body }) => {
          screenBody = body
        },
      },
      {
        path: '/api/opportunities/applications/app-1/status',
        method: 'POST',
        body: makeCompanyApplication({ status: 'shortlisted' }),
        onCall: ({ body }) => moved.push(JSON.stringify(body)),
      },
      { path: '/api/opportunities/applications', body: page([makeCompanyApplication()]) },
    ])
    renderApp(PAGE)
    await screen.findByText('Aarav Mehta')

    const form = within(screen.getByRole('form', { name: 'Screen applicants' }))
    await user.type(form.getByLabelText('Threshold (0 to 100)'), '60')
    await user.click(form.getByRole('checkbox', { name: 'UG' }))
    await user.click(form.getByRole('button', { name: 'Screen' }))

    await waitFor(() => expect(screenBody).toEqual({ threshold: 60, required_education_levels: ['UG'] }))
    expect(await screen.findByText('Shortlisted (1)')).toBeInTheDocument()
    expect(screen.getByText('Filtered out (1)')).toBeInTheDocument()
    expect(screen.getByText('Needs 3 years of experience.')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: /move screened applicants to shortlisted/i }))
    expect(await screen.findByText('Moved 1 applicant to Shortlisted.')).toBeInTheDocument()
    expect(moved).toEqual([JSON.stringify({ status: 'shortlisted', note: 'Passed screening' })])
  })

  it('has an empty state', async () => {
    signedInAs(COMPANY_USER, [{ path: '/api/opportunities/applications', body: page([]) }])
    renderApp(PAGE)
    expect(await screen.findByText('No applicants yet')).toBeInTheDocument()
  })
})
