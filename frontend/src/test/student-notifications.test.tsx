import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import type { AppNotification } from '@/api/notifications'
import { makeUser, renderApp } from '@/test/harness'
import { page, signedInAs } from '@/test/opportunity-fixtures'

const STUDENT = makeUser()

function note(overrides: Partial<AppNotification> = {}): AppNotification {
  return {
    id: 'n-1',
    kind: 'new_opportunity',
    opportunity: { id: 'opp-1', title: 'Backend Engineer' },
    created_at: '2026-11-01T10:00:00Z',
    read_at: null,
    ...overrides,
  }
}

beforeEach(() => localStorage.clear())
afterEach(() => {
  vi.unstubAllGlobals()
  localStorage.clear()
})

describe('notifications', () => {
  it('lists notifications and shows the unread count in the nav', async () => {
    signedInAs(STUDENT, [
      {
        path: '/api/notifications/?unread=true',
        body: page([note(), note({ id: 'n-2', kind: 'deadline_soon' })]),
      },
      {
        path: '/api/notifications/',
        body: page([note(), note({ id: 'n-2', kind: 'deadline_soon' }), note({ id: 'n-3', read_at: '2026-11-02T00:00:00Z' })]),
      },
    ])
    renderApp('/student/notifications')

    expect(await screen.findAllByText(/new opportunity open to you: backend engineer/i)).toHaveLength(2)
    expect(screen.getByText(/deadline coming up: backend engineer/i)).toBeInTheDocument()
    expect(screen.getByText('2 unread', { selector: 'p' })).toBeInTheDocument()
    // The nav badge carries the same count for screen readers.
    expect(screen.getByRole('link', { name: /notifications/i })).toHaveTextContent('2 unread')
  })

  it('marks one notification read', async () => {
    const user = userEvent.setup()
    const calls: string[] = []
    signedInAs(STUDENT, [
      {
        path: '/api/notifications/n-1/read',
        method: 'POST',
        status: 204,
        onCall: () => calls.push('read'),
      },
      { path: '/api/notifications/', body: page([note()]) },
    ])
    renderApp('/student/notifications')

    await user.click(await screen.findByRole('button', { name: 'Mark read' }))

    await waitFor(() => expect(calls).toEqual(['read']))
  })

  it('marks everything read', async () => {
    const user = userEvent.setup()
    const calls: string[] = []
    signedInAs(STUDENT, [
      {
        path: '/api/notifications/read-all',
        method: 'POST',
        status: 204,
        onCall: () => calls.push('all'),
      },
      { path: '/api/notifications/', body: page([note()]) },
    ])
    renderApp('/student/notifications')

    await user.click(await screen.findByRole('button', { name: 'Mark all read' }))

    await waitFor(() => expect(calls).toEqual(['all']))
  })

  it('has an empty state and no badge when nothing is unread', async () => {
    signedInAs(STUDENT, [{ path: '/api/notifications/', body: page([]) }])
    renderApp('/student/notifications')
    expect(await screen.findByText('No notifications')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Mark all read' })).toBeDisabled()
    expect(screen.getByRole('link', { name: 'Notifications' })).not.toHaveTextContent('unread')
  })
})
