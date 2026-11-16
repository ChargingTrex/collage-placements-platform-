import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { makeUser, renderApp } from '@/test/harness'
import { makeStudentApplication, page, signedInAs } from '@/test/opportunity-fixtures'

const STUDENT = makeUser()
const NO_NOTES = { path: '/api/notifications/', body: page([]) }

beforeEach(() => localStorage.clear())
afterEach(() => {
  vi.unstubAllGlobals()
  localStorage.clear()
})

describe('my applications', () => {
  it('lists each application with its history', async () => {
    signedInAs(STUDENT, [
      NO_NOTES,
      {
        path: '/api/opportunities/applications',
        body: page([
          makeStudentApplication({
            status: 'shortlisted',
            events: [
              { from_status: '', to_status: 'applied', note: '', created_at: '2026-11-01T10:00:00Z' },
              {
                from_status: 'applied',
                to_status: 'shortlisted',
                note: 'Strong fit',
                created_at: '2026-11-03T10:00:00Z',
              },
            ],
          }),
        ]),
      },
    ])
    renderApp('/student/applications')

    expect(await screen.findByRole('heading', { name: 'Backend Engineer' })).toBeInTheDocument()
    const history = screen.getByRole('list', { name: 'History' })
    expect(history).toHaveTextContent('Applied')
    expect(history).toHaveTextContent('Shortlisted')
    expect(history).toHaveTextContent('Strong fit')
  })

  it('withdraws after a confirmation', async () => {
    const user = userEvent.setup()
    signedInAs(STUDENT, [
      NO_NOTES,
      {
        path: '/api/opportunities/applications/app-1/withdraw',
        method: 'POST',
        body: makeStudentApplication({ status: 'withdrawn' }),
      },
      { path: '/api/opportunities/applications', body: page([makeStudentApplication()]) },
    ])
    renderApp('/student/applications')

    await user.click(await screen.findByRole('button', { name: 'Withdraw' }))
    await user.click(screen.getByRole('button', { name: 'Confirm withdraw' }))

    await waitFor(() => expect(screen.getAllByText('Withdrawn').length).toBeGreaterThan(0))
    expect(screen.queryByRole('button', { name: 'Withdraw' })).not.toBeInTheDocument()
  })

  it('offers no withdraw once an application is final', async () => {
    signedInAs(STUDENT, [
      NO_NOTES,
      {
        path: '/api/opportunities/applications',
        body: page([makeStudentApplication({ status: 'offer' })]),
      },
    ])
    renderApp('/student/applications')
    await screen.findByRole('heading', { name: 'Backend Engineer' })
    expect(screen.queryByRole('button', { name: 'Withdraw' })).not.toBeInTheDocument()
  })

  it('has an empty state', async () => {
    signedInAs(STUDENT, [NO_NOTES, { path: '/api/opportunities/applications', body: page([]) }])
    renderApp('/student/applications')
    expect(await screen.findByText('No applications yet')).toBeInTheDocument()
  })
})
