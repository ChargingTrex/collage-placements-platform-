import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { makeUser, renderApp } from '@/test/harness'
import {
  makeFeedRow,
  makeStudentApplication,
  OPP_ID,
  page,
  signedInAs,
} from '@/test/opportunity-fixtures'

const STUDENT = makeUser()
const NO_NOTES = { path: '/api/notifications/', body: page([]) }

beforeEach(() => localStorage.clear())
afterEach(() => {
  vi.unstubAllGlobals()
  localStorage.clear()
})

function noProbability() {
  expect(document.body.textContent?.toLowerCase()).not.toContain('probability')
}

describe('student suggestions', () => {
  it('shows ranked suggestions with the shared card, honest framing and no "probability"', async () => {
    signedInAs(STUDENT, [
      NO_NOTES,
      {
        path: '/api/opportunities/suggestions',
        body: { results: [makeFeedRow()], open_count: 3, reason: null },
      },
    ])
    renderApp('/student/suggestions')

    const list = within(await screen.findByRole('list', { name: 'Suggested postings' }))
    expect(list.getByText('Backend Engineer')).toBeInTheDocument()
    expect(list.getByText('Match 72 of 100')).toBeInTheDocument()
    expect(list.getByText('Eligible')).toBeInTheDocument()
    expect(screen.getAllByText(/not a prediction/i).length).toBeGreaterThan(0)
    expect(screen.getByRole('link', { name: 'Suggestions' })).toBeInTheDocument()
    noProbability()
  })

  it('can apply from a suggestion', async () => {
    const user = userEvent.setup()
    signedInAs(STUDENT, [
      NO_NOTES,
      {
        path: `/api/opportunities/${OPP_ID}/apply`,
        method: 'POST',
        status: 201,
        body: makeStudentApplication(),
      },
      {
        path: '/api/opportunities/suggestions',
        body: { results: [makeFeedRow()], open_count: 1, reason: null },
      },
    ])
    renderApp('/student/suggestions')

    await user.click(await screen.findByRole('button', { name: 'Apply' }))

    await waitFor(() => expect(screen.getByText('Your application:')).toBeInTheDocument())
  })

  it('explains an apply refusal on the card', async () => {
    const user = userEvent.setup()
    signedInAs(STUDENT, [
      NO_NOTES,
      {
        path: `/api/opportunities/${OPP_ID}/apply`,
        method: 'POST',
        status: 400,
        body: { detail: 'x', reason: 'no_resume' },
      },
      {
        path: '/api/opportunities/suggestions',
        body: { results: [makeFeedRow()], open_count: 1, reason: null },
      },
    ])
    renderApp('/student/suggestions')

    await user.click(await screen.findByRole('button', { name: 'Apply' }))

    expect(await screen.findByRole('alert')).toHaveTextContent(/upload a resume/i)
  })

  it('says nothing has been posted when there are no open postings', async () => {
    signedInAs(STUDENT, [
      NO_NOTES,
      {
        path: '/api/opportunities/suggestions',
        body: { results: [], open_count: 0, reason: 'no_open_postings' },
      },
    ])
    renderApp('/student/suggestions')

    expect(await screen.findByText('Nothing has been posted yet')).toBeInTheDocument()
    expect(screen.queryByText('Nothing fits you well right now')).not.toBeInTheDocument()
    noProbability()
  })

  it('says nothing fits well when postings exist, and links to the jobs board', async () => {
    signedInAs(STUDENT, [
      NO_NOTES,
      {
        path: '/api/opportunities/suggestions',
        body: { results: [], open_count: 4, reason: 'none_match' },
      },
    ])
    renderApp('/student/suggestions')

    expect(await screen.findByText('Nothing fits you well right now')).toBeInTheDocument()
    expect(screen.queryByText('Nothing has been posted yet')).not.toBeInTheDocument()
    expect(screen.getByText(/4 open postings/)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'See all open jobs' })).toHaveAttribute(
      'href',
      '/student/jobs',
    )
    noProbability()
  })

  it('shows a plain message when throttled', async () => {
    signedInAs(STUDENT, [
      NO_NOTES,
      { path: '/api/opportunities/suggestions', status: 429, body: { detail: 'Throttled' } },
    ])
    renderApp('/student/suggestions')
    expect(await screen.findByRole('alert')).toHaveTextContent(/try again in a minute/i)
  })
})
