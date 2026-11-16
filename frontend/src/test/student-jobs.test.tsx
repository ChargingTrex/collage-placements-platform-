import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { renderApp, makeUser } from '@/test/harness'
import {
  makeFeedRow,
  makeStudentApplication,
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

describe('student jobs board', () => {
  it('shows eligibility beside the match score, not inside it', async () => {
    signedInAs(STUDENT, [
      NO_NOTES,
      {
        path: '/api/opportunities/feed',
        body: page([
          makeFeedRow({
            eligible: false,
            eligibility_reasons: ['Your CGPA 6.2 is below the 7.0 this posting asks for.'],
          }),
        ]),
      },
    ])
    renderApp('/student/jobs')

    const card = within(await screen.findByRole('list', { name: 'Open postings' }))
    expect(card.getByText('Backend Engineer')).toBeInTheDocument()
    expect(card.getByText('Match 72 of 100')).toBeInTheDocument()
    expect(card.getByText('Not eligible')).toBeInTheDocument()
    expect(card.getByText(/CGPA 6\.2 is below the 7\.0/)).toBeInTheDocument()
    expect(card.getByRole('button', { name: 'Apply' })).toBeDisabled()
    expect(document.body.textContent?.toLowerCase()).not.toContain('probability')
  })

  it('applies and then shows the application status instead of the button', async () => {
    const user = userEvent.setup()
    signedInAs(STUDENT, [
      NO_NOTES,
      {
        path: '/api/opportunities/9b1d0a52-1111-4a6c-8f00-000000000001/apply',
        method: 'POST',
        status: 201,
        body: makeStudentApplication(),
      },
      { path: '/api/opportunities/feed', body: page([makeFeedRow()]) },
    ])
    renderApp('/student/jobs')

    await user.click(await screen.findByRole('button', { name: 'Apply' }))

    await waitFor(() => expect(screen.getByText('Your application:')).toBeInTheDocument())
    expect(screen.getByText('Applied')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Apply' })).not.toBeInTheDocument()
  })

  it.each([
    ['not_open', /not open for applications/i],
    ['deadline_passed', /deadline .* has passed/i],
    ['already_applied', /already applied/i],
    ['no_resume', /upload a resume/i],
    ['not_eligible', /department or CGPA requirement/i],
  ])('explains the %s refusal in plain words', async (reason, words) => {
    const user = userEvent.setup()
    signedInAs(STUDENT, [
      NO_NOTES,
      {
        path: '/api/opportunities/9b1d0a52-1111-4a6c-8f00-000000000001/apply',
        method: 'POST',
        status: 400,
        body: { detail: 'raw server text', reason },
      },
      { path: '/api/opportunities/feed', body: page([makeFeedRow()]) },
    ])
    renderApp('/student/jobs')

    await user.click(await screen.findByRole('button', { name: 'Apply' }))

    expect(await screen.findByRole('alert')).toHaveTextContent(words)
  })

  it('says so when nothing is open', async () => {
    signedInAs(STUDENT, [NO_NOTES, { path: '/api/opportunities/feed', body: page([]) }])
    renderApp('/student/jobs')
    expect(await screen.findByText('Nothing to show')).toBeInTheDocument()
  })

  it('filters the board by the search box', async () => {
    const user = userEvent.setup()
    signedInAs(STUDENT, [
      NO_NOTES,
      {
        path: '/api/opportunities/feed',
        body: page([
          makeFeedRow(),
          makeFeedRow({ id: 'opp-2', title: 'Data Analyst', required_skills: ['sql'] }),
        ]),
      },
    ])
    renderApp('/student/jobs')
    await screen.findByText('Data Analyst')

    await user.type(screen.getByLabelText('Search'), 'analyst')

    expect(screen.queryByText('Backend Engineer')).not.toBeInTheDocument()
    expect(screen.getByText('Data Analyst')).toBeInTheDocument()
  })
})
