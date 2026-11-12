import '@testing-library/jest-dom/vitest'
import { screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { makeOwnProfile } from '@/test/fixtures'
import { HEALTHY, makeUser, mockApi, renderApp, type Route } from '@/test/harness'

function signedInAsStudent(extra: Route[] = []) {
  localStorage.setItem('pcp.access', 'access-token')
  return mockApi([HEALTHY, { path: '/api/auth/me', body: makeUser() }, ...extra])
}

beforeEach(() => localStorage.clear())
afterEach(() => {
  vi.unstubAllGlobals()
  localStorage.clear()
})

async function openCard() {
  const heading = await screen.findByText('After graduation')
  return heading.closest('section') as HTMLElement
}

describe('career path card', () => {
  it('lists all nine options, with the three look-alikes explained', async () => {
    signedInAsStudent([{ path: '/api/profiles/me', body: makeOwnProfile() }])
    renderApp('/student/profile')

    const card = await openCard()
    expect(within(card).getAllByRole('radio')).toHaveLength(9)
    expect(within(card).getByText("Joining an existing business that is not your family's.")).toBeInTheDocument()
    expect(within(card).getByText('Founding a new venture of your own.')).toBeInTheDocument()
    expect(within(card).getByText("Joining or succeeding in your family's business.")).toBeInTheDocument()
    expect(within(card).queryByLabelText('What are you planning?')).not.toBeInTheDocument()
  })

  it('saves a path with the placements checkbox', async () => {
    const user = userEvent.setup()
    const sent: unknown[] = []
    signedInAsStudent([
      {
        path: '/api/profiles/me',
        method: 'PATCH',
        body: makeOwnProfile({ career_path: 'competitive_exams', also_attending_placements: true }),
        onCall: ({ body }) => sent.push(body),
      },
      { path: '/api/profiles/me', method: 'GET', body: makeOwnProfile() },
    ])
    renderApp('/student/profile')

    const card = await openCard()
    await user.click(within(card).getByRole('radio', { name: /competitive exams/i }))
    await user.click(within(card).getByLabelText('I am also attending placements'))
    await user.click(within(card).getByRole('button', { name: 'Save career path' }))

    expect(await within(card).findByText('Saved.')).toBeInTheDocument()
    expect(sent).toEqual([
      { career_path: 'competitive_exams', career_path_detail: '', also_attending_placements: true },
    ])
  })

  it('will not save "Other" without text', async () => {
    const user = userEvent.setup()
    const sent: unknown[] = []
    signedInAsStudent([
      {
        path: '/api/profiles/me',
        method: 'PATCH',
        onCall: ({ body }) => sent.push(body),
      },
      { path: '/api/profiles/me', method: 'GET', body: makeOwnProfile() },
    ])
    renderApp('/student/profile')

    const card = await openCard()
    await user.click(within(card).getByRole('radio', { name: /^Other/ }))
    expect(within(card).getByLabelText('What are you planning?')).toBeRequired()
    await user.click(within(card).getByRole('button', { name: 'Save career path' }))

    expect(await within(card).findByText('Tell us what "Other" means.')).toBeInTheDocument()
    expect(sent).toEqual([])
  })
})
