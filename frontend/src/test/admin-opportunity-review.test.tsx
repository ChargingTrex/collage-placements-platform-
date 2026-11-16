import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { renderApp } from '@/test/harness'
import { ADMIN_USER, makeOpportunity, page, signedInAs } from '@/test/opportunity-fixtures'

beforeEach(() => localStorage.clear())
afterEach(() => {
  vi.unstubAllGlobals()
  localStorage.clear()
})

describe('admin review queue', () => {
  it('approves a pending posting', async () => {
    const user = userEvent.setup()
    const calls: string[] = []
    signedInAs(ADMIN_USER, [
      {
        path: '/api/opportunities/p1/approve',
        method: 'POST',
        body: makeOpportunity({ status: 'open' }),
        onCall: () => calls.push('approve'),
      },
      {
        path: '/api/opportunities/?status=pending_review',
        body: page([makeOpportunity({ id: 'p1', title: 'Pending role', status: 'pending_review' })]),
      },
    ])
    renderApp('/admin/opportunities/review')

    const card = within((await screen.findByText('Pending role')).closest('li')!)
    await user.click(card.getByRole('button', { name: 'Approve' }))

    await waitFor(() => expect(calls).toEqual(['approve']))
    expect(await screen.findByText(/approved/i, { selector: '[role=status] *, [role=status]' })).toBeInTheDocument()
  })

  it('will not reject without a reason, then sends the reason', async () => {
    const user = userEvent.setup()
    let sent: unknown
    signedInAs(ADMIN_USER, [
      {
        path: '/api/opportunities/p1/reject',
        method: 'POST',
        body: makeOpportunity({ status: 'rejected' }),
        onCall: ({ body }) => {
          sent = body
        },
      },
      {
        path: '/api/opportunities/?status=pending_review',
        body: page([makeOpportunity({ id: 'p1', title: 'Pending role', status: 'pending_review' })]),
      },
    ])
    renderApp('/admin/opportunities/review')

    await user.click(await screen.findByRole('button', { name: 'Reject' }))
    await user.click(screen.getByRole('button', { name: 'Confirm reject' }))
    expect(await screen.findByRole('alert')).toHaveTextContent(/give a reason/i)
    expect(sent).toBeUndefined()

    await user.type(screen.getByLabelText('Reason for rejecting'), 'Add a salary range.')
    await user.click(screen.getByRole('button', { name: 'Confirm reject' }))
    await waitFor(() => expect(sent).toEqual({ reason: 'Add a salary range.' }))
  })

  it('has an empty state', async () => {
    signedInAs(ADMIN_USER, [{ path: '/api/opportunities/', body: page([]) }])
    renderApp('/admin/opportunities/review')
    expect(await screen.findByText('Nothing waiting for review')).toBeInTheDocument()
  })
})

