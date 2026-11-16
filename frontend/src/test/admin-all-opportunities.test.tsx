import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { renderApp } from '@/test/harness'
import { ADMIN_USER, makeOpportunity, page, signedInAs } from '@/test/opportunity-fixtures'

beforeEach(() => localStorage.clear())
afterEach(() => {
  vi.unstubAllGlobals()
  localStorage.clear()
})

describe('admin all postings', () => {
  it('lists postings across companies and filters by status on the server', async () => {
    const user = userEvent.setup()
    const fetchMock = signedInAs(ADMIN_USER, [
      {
        path: '/api/opportunities/',
        body: page([makeOpportunity({ title: 'Acme role', status: 'open' })]),
      },
    ])
    renderApp('/admin/opportunities')

    expect(await screen.findByText('Acme role')).toBeInTheDocument()
    await user.selectOptions(screen.getByLabelText('Status'), 'closed')

    await waitFor(() =>
      expect(fetchMock.mock.calls.some((call) => String(call[0]).includes('status=closed'))).toBe(true),
    )
  })

  it('creates a posting for a company, sending the company id', async () => {
    const user = userEvent.setup()
    let sent: Record<string, unknown> | undefined
    signedInAs(ADMIN_USER, [
      {
        path: '/api/opportunities/',
        method: 'POST',
        status: 201,
        body: makeOpportunity({ status: 'open' }),
        onCall: ({ body }) => {
          sent = body as Record<string, unknown>
        },
      },
      { path: '/api/opportunities/', body: page([]) },
    ])
    renderApp('/admin/opportunities')

    await user.click(await screen.findByRole('button', { name: 'New posting' }))
    // Without a company the form refuses before calling the server.
    await user.type(screen.getByLabelText('Title'), 'Platform Engineer')
    await user.type(screen.getByLabelText('Description'), 'Run the platform.')
    await user.type(screen.getByLabelText('Deadline'), '2026-12-31')
    await user.click(screen.getByRole('button', { name: 'Create posting' }))
    expect(await screen.findByText('Enter the company this posting is for.')).toBeInTheDocument()
    expect(sent).toBeUndefined()

    await user.type(screen.getByLabelText('Company ID'), '7a1b2c3d-0000-4000-8000-00000000c0de')
    await user.click(screen.getByRole('button', { name: 'Create posting' }))

    await waitFor(() => expect(sent?.company).toBe('7a1b2c3d-0000-4000-8000-00000000c0de'))
    expect(await screen.findByText(/Saved/)).toBeInTheDocument()
  })

  it('closes an open posting and links to its applicants', async () => {
    const user = userEvent.setup()
    const calls: string[] = []
    signedInAs(ADMIN_USER, [
      {
        path: '/api/opportunities/b/close',
        method: 'POST',
        body: makeOpportunity({ status: 'closed' }),
        onCall: () => calls.push('close'),
      },
      { path: '/api/opportunities/', body: page([makeOpportunity({ id: 'b', status: 'open' })]) },
    ])
    renderApp('/admin/opportunities')

    expect(await screen.findByRole('link', { name: 'Applicants' })).toHaveAttribute(
      'href',
      '/admin/opportunities/b/applicants',
    )
    await user.click(screen.getByRole('button', { name: 'Close' }))
    await waitFor(() => expect(calls).toEqual(['close']))
  })
})

