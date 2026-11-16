import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { renderApp } from '@/test/harness'
import {
  COMPANY_USER,
  makeOpportunity,
  page,
  signedInAs,
} from '@/test/opportunity-fixtures'

beforeEach(() => localStorage.clear())
afterEach(() => {
  vi.unstubAllGlobals()
  localStorage.clear()
})

describe('company postings', () => {
  it('offers only the actions each status allows', async () => {
    signedInAs(COMPANY_USER, [
      {
        path: '/api/opportunities/',
        body: page([
          makeOpportunity({ id: 'a', title: 'Draft role', status: 'draft' }),
          makeOpportunity({ id: 'b', title: 'Live role', status: 'open' }),
          makeOpportunity({
            id: 'c',
            title: 'Bounced role',
            status: 'rejected',
            rejection_reason: 'Add a salary range.',
          }),
          makeOpportunity({ id: 'd', title: 'Waiting role', status: 'pending_review' }),
        ]),
      },
    ])
    renderApp('/company/opportunities')

    const draft = within((await screen.findByText('Draft role')).closest('li')!)
    expect(draft.getByRole('button', { name: 'Submit for review' })).toBeInTheDocument()
    expect(draft.getByRole('button', { name: 'Delete draft' })).toBeInTheDocument()

    const live = within(screen.getByText('Live role').closest('li')!)
    expect(live.getByRole('button', { name: 'Close' })).toBeInTheDocument()
    expect(live.getByRole('link', { name: 'Applicants' })).toHaveAttribute(
      'href',
      '/company/opportunities/b/applicants',
    )
    expect(live.queryByRole('button', { name: 'Edit' })).not.toBeInTheDocument()

    const bounced = within(screen.getByText('Bounced role').closest('li')!)
    expect(bounced.getByText('Add a salary range.')).toBeInTheDocument()
    expect(bounced.getByRole('button', { name: 'Edit' })).toBeInTheDocument()

    const waiting = within(screen.getByText('Waiting role').closest('li')!)
    expect(waiting.getByText(/waiting for the placement cell/i)).toBeInTheDocument()
    expect(waiting.queryByRole('button')).not.toBeInTheDocument()
  })

  it('creates a posting from the form', async () => {
    const user = userEvent.setup()
    let sent: Record<string, unknown> | undefined
    signedInAs(COMPANY_USER, [
      {
        path: '/api/opportunities/',
        method: 'POST',
        status: 201,
        body: makeOpportunity(),
        onCall: ({ body }) => {
          sent = body as Record<string, unknown>
        },
      },
      { path: '/api/opportunities/', body: page([]) },
    ])
    renderApp('/company/opportunities')

    await user.click(await screen.findByRole('button', { name: 'New posting' }))
    await user.type(screen.getByLabelText('Title'), 'Backend Engineer')
    await user.type(screen.getByLabelText('Description'), 'Build Django services.')
    await user.type(screen.getByLabelText('Deadline'), '2026-12-31')
    await user.type(screen.getByLabelText('Required skills'), 'python, sql')
    await user.type(screen.getByLabelText('Minimum CGPA'), '7')
    await user.click(screen.getByRole('button', { name: 'Create posting' }))

    await waitFor(() => expect(sent).toBeDefined())
    expect(sent).toMatchObject({
      title: 'Backend Engineer',
      deadline: '2026-12-31',
      required_skills: ['python', 'sql'],
      min_cgpa: 7,
      salary_disclosed: false,
      salary_min: null,
    })
    expect(sent).not.toHaveProperty('company')
    expect(await screen.findByText(/submit it for review when it is ready/i)).toBeInTheDocument()
  })

  it('submits a draft for review', async () => {
    const user = userEvent.setup()
    const calls: string[] = []
    signedInAs(COMPANY_USER, [
      {
        path: '/api/opportunities/a/submit',
        method: 'POST',
        body: makeOpportunity({ status: 'pending_review' }),
        onCall: () => calls.push('submit'),
      },
      { path: '/api/opportunities/', body: page([makeOpportunity({ id: 'a', status: 'draft' })]) },
    ])
    renderApp('/company/opportunities')

    await user.click(await screen.findByRole('button', { name: 'Submit for review' }))

    await waitFor(() => expect(calls).toEqual(['submit']))
    expect(await screen.findByText('Submitted for review.')).toBeInTheDocument()
  })

  it('closes an open posting', async () => {
    const user = userEvent.setup()
    const calls: string[] = []
    signedInAs(COMPANY_USER, [
      {
        path: '/api/opportunities/b/close',
        method: 'POST',
        body: makeOpportunity({ status: 'closed' }),
        onCall: () => calls.push('close'),
      },
      { path: '/api/opportunities/', body: page([makeOpportunity({ id: 'b', status: 'open' })]) },
    ])
    renderApp('/company/opportunities')

    await user.click(await screen.findByRole('button', { name: 'Close' }))
    await waitFor(() => expect(calls).toEqual(['close']))
  })

  it('shows the server message when the company has no access', async () => {
    signedInAs(COMPANY_USER, [
      {
        path: '/api/opportunities/',
        status: 403,
        body: { detail: 'Your account is not linked to a company.' },
      },
    ])
    renderApp('/company/opportunities')
    expect(await screen.findByRole('alert')).toHaveTextContent('not linked to a company')
  })

  it('has an empty state', async () => {
    signedInAs(COMPANY_USER, [{ path: '/api/opportunities/', body: page([]) }])
    renderApp('/company/opportunities')
    expect(await screen.findByText('No postings yet')).toBeInTheDocument()
  })
})
