import '@testing-library/jest-dom/vitest'
import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { makeOwnProfile, STUDENT_ID } from '@/test/fixtures'
import { HEALTHY, makeUser, mockApi, renderApp, type Route } from '@/test/harness'
import {
  CGPA_FLAG,
  EMAIL_FLAG,
  makeAdminDetail,
  makeAdminProfile,
  RESUME_FACTS,
} from '@/test/intelligence-fixtures'

const ADMIN = makeUser({
  roles: ['placement_admin'],
  prn: null,
  email: 'placement.officer@college.edu',
  full_name: 'Priya Kulkarni',
})

const STATS = {
  path: '/api/profiles/admin/stats',
  body: {
    profiles: 2,
    verified: 0,
    with_resume: 2,
    fully_complete: 0,
    average_completion_percent: 40,
    visibility: { all: 2 },
  },
} satisfies Route

const OTHER_ID = '9b1d2e3f-4a5b-4c6d-8e7f-0a1b2c3d4e5f'
const FLAGGED = makeAdminProfile({ verification_checks: [CGPA_FLAG, EMAIL_FLAG], warning_count: 1 })
const CLEAN = makeAdminProfile({
  id: 'p-2',
  student_id: OTHER_ID,
  student: { ...makeOwnProfile().student, prn: '220200922', full_name: 'Diya Shah' },
})

function signedInAsAdmin(extra: Route[] = []) {
  localStorage.setItem('pcp.access', 'access-token')
  return mockApi([
    HEALTHY,
    { path: '/api/auth/me', body: ADMIN },
    STATS,
    ...extra,
    {
      path: '/api/profiles/admin',
      body: { count: 2, next: null, previous: null, results: [FLAGGED, CLEAN] },
    },
  ])
}

function cardFor(name: string): HTMLElement {
  return screen.getByText(name).closest('section') as HTMLElement
}

beforeEach(() => localStorage.clear())
afterEach(() => {
  vi.unstubAllGlobals()
  localStorage.clear()
})

describe('admin verification flags', () => {
  it('shows a warning-count badge on every profile', async () => {
    signedInAsAdmin()
    renderApp('/admin/profiles')

    await waitFor(() => expect(screen.getByText('Diya Shah')).toBeInTheDocument())
    expect(within(cardFor('Aarav Mehta')).getByText('1 warning')).toBeInTheDocument()
    expect(within(cardFor('Diya Shah')).getByText('0 warnings')).toBeInTheDocument()
  })

  it('expands the flag list from the profile detail, with severity, sources and values', async () => {
    const user = userEvent.setup()
    const detailCalls: Array<{ method: string; body: unknown }> = []
    signedInAsAdmin([
      {
        path: `/api/profiles/admin/${STUDENT_ID}`,
        body: makeAdminDetail(),
        onCall: (call) => detailCalls.push(call),
      },
    ])
    renderApp('/admin/profiles')

    await waitFor(() => expect(screen.getByText('Aarav Mehta')).toBeInTheDocument())
    const card = cardFor('Aarav Mehta')
    const toggle = within(card).getByRole('button', { name: /show verification checks \(2\)/i })
    expect(toggle).toHaveAttribute('aria-expanded', 'false')
    expect(detailCalls).toHaveLength(0)

    await user.click(toggle)
    expect(toggle).toHaveAttribute('aria-expanded', 'true')

    const flags = await within(card).findByRole('list', { name: 'Verification flags' })
    expect(detailCalls).toHaveLength(1)
    const [cgpa, email] = within(flags).getAllByRole('listitem')
    expect(within(cgpa).getByText('Warning')).toBeInTheDocument()
    expect(within(cgpa).getByText(CGPA_FLAG.message)).toBeInTheDocument()
    expect(within(cgpa).getByText('Sources: Roster vs Resume')).toBeInTheDocument()
    expect(within(cgpa).getByText('8.72')).toBeInTheDocument()
    expect(within(cgpa).getByText('9.4')).toBeInTheDocument()
    expect(within(email).getByText('Info')).toBeInTheDocument()
    expect(within(email).getByText('aarav.m@gmail.example')).toBeInTheDocument()
  })

  it('shows the admin-only resume facts under a for-verification-only label', async () => {
    const user = userEvent.setup()
    signedInAsAdmin([{ path: `/api/profiles/admin/${STUDENT_ID}`, body: makeAdminDetail() }])
    renderApp('/admin/profiles')

    await waitFor(() => expect(screen.getByText('Aarav Mehta')).toBeInTheDocument())
    const card = cardFor('Aarav Mehta')
    await user.click(within(card).getByRole('button', { name: /show verification checks/i }))

    const facts = await within(card).findByRole('region', {
      name: 'From the resume — for verification only',
    })
    const value = (label: string) => within(facts).getByText(label).nextElementSibling
    expect(value('Age')).toHaveTextContent(String(RESUME_FACTS.age))
    expect(value('Date of birth')).toHaveTextContent(RESUME_FACTS.date_of_birth!)
    expect(value('CGPA on the resume')).toHaveTextContent(String(RESUME_FACTS.cgpa))
    expect(value('Phones')).toHaveTextContent(RESUME_FACTS.phones[0])
    expect(value('Emails')).toHaveTextContent(RESUME_FACTS.emails[0])
  })

  it('says when a profile has nothing to compare yet', async () => {
    const user = userEvent.setup()
    signedInAsAdmin([
      {
        path: `/api/profiles/admin/${OTHER_ID}`,
        body: makeAdminDetail({ ...CLEAN, verification_checks: [], warning_count: 0, resume_facts_admin: null }),
      },
    ])
    renderApp('/admin/profiles')

    await waitFor(() => expect(screen.getByText('Diya Shah')).toBeInTheDocument())
    const card = cardFor('Diya Shah')
    await user.click(within(card).getByRole('button', { name: /show verification checks/i }))

    expect(await within(card).findByText(/has not been analysed yet/i)).toBeInTheDocument()
    expect(within(card).queryByText(/for verification only/i)).not.toBeInTheDocument()
  })

  it('never lets the flags block the verify button', async () => {
    const user = userEvent.setup()
    const calls: Array<{ method: string; body: unknown }> = []
    signedInAsAdmin([
      {
        path: `/api/profiles/admin/${STUDENT_ID}/verification`,
        method: 'POST',
        body: makeAdminDetail({ is_verified: true }),
        onCall: (call) => calls.push(call),
      },
      { path: `/api/profiles/admin/${STUDENT_ID}`, body: makeAdminDetail() },
    ])
    renderApp('/admin/profiles')

    await waitFor(() => expect(screen.getByText('Aarav Mehta')).toBeInTheDocument())
    const card = cardFor('Aarav Mehta')
    await user.click(within(card).getByRole('button', { name: /show verification checks/i }))
    await within(card).findByRole('list', { name: 'Verification flags' })

    const verify = within(card).getByRole('button', { name: 'Mark verified' })
    expect(verify).toBeEnabled()
    await user.click(verify)

    await waitFor(() => expect(calls).toHaveLength(1))
    expect(calls[0].body).toEqual({ is_verified: true, note: '' })
  })
})
