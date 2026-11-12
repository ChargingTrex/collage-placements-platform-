import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { makeCompanyProfile, makeOwnProfile, STUDENT_ID } from '@/test/fixtures'
import { HEALTHY, makeUser, mockApi, renderApp, type Route } from '@/test/harness'

const COMPANY = makeUser({
  roles: ['company_recruiter:7a1b2c3d-0000-4000-8000-00000000c0de'],
  prn: null,
  email: 'recruiter@acmetech.example',
  full_name: 'Acme Tech',
})
const ADMIN = makeUser({
  roles: ['placement_admin'],
  prn: null,
  email: 'placement.officer@college.edu',
  full_name: 'Priya Kulkarni',
})

function signedInAs(user: ReturnType<typeof makeUser>, extra: Route[] = []) {
  localStorage.setItem('pcp.access', 'access-token')
  return mockApi([HEALTHY, { path: '/api/auth/me', body: user }, ...extra])
}

beforeEach(() => localStorage.clear())
afterEach(() => {
  vi.unstubAllGlobals()
  localStorage.clear()
})

describe('company student search', () => {
  it('lists visible profiles with their headline, CGPA and skills', async () => {
    signedInAs(COMPANY, [
      {
        path: '/api/profiles/students',
        body: { count: 1, next: null, previous: null, results: [makeCompanyProfile()] },
      },
    ])
    renderApp('/company/students')

    await waitFor(() => expect(screen.getByText('Aarav Mehta')).toBeInTheDocument())
    expect(screen.getByText('1 profile')).toBeInTheDocument()
    expect(screen.getByText(/backend developer · computer engineering/i)).toBeInTheDocument()
    expect(screen.getByText(/CGPA 8\.72 · 3\.0 yrs experience/)).toBeInTheDocument()
    expect(screen.getByText('Django')).toBeInTheDocument()
  })

  it('sends the PRD filter set to the server', async () => {
    const user = userEvent.setup()
    const urls: string[] = []
    const fetchMock = signedInAs(COMPANY, [
      {
        path: '/api/profiles/students',
        body: { count: 0, next: null, previous: null, results: [] },
      },
    ])
    renderApp('/company/students')

    await waitFor(() => expect(screen.getByLabelText(/^department$/i)).toBeInTheDocument())
    await user.type(screen.getByLabelText(/^department$/i), 'Computer Engineering')
    await user.type(screen.getByLabelText(/^skills$/i), 'python,django')
    await user.type(screen.getByLabelText(/project keyword/i), 'dashboard')
    await user.type(screen.getByLabelText(/cgpa from/i), '8')
    await user.click(screen.getByRole('button', { name: /apply/i }))

    await waitFor(() => {
      for (const call of fetchMock.mock.calls) urls.push(String(call[0]))
      const applied = urls.find((url) => url.includes('department='))
      expect(applied).toBeDefined()
      expect(applied).toContain('skills=python%2Cdjango')
      expect(applied).toContain('project_keyword=dashboard')
      expect(applied).toContain('cgpa_min=8')
    })
  })

  it('says nothing matched rather than showing an empty list', async () => {
    signedInAs(COMPANY, [
      {
        path: '/api/profiles/students',
        body: { count: 0, next: null, previous: null, results: [] },
      },
    ])
    renderApp('/company/students')

    await waitFor(() => expect(screen.getByText(/no profiles match/i)).toBeInTheDocument())
    expect(screen.getByText(/set their profile to hidden never appear/i)).toBeInTheDocument()
  })

  it('shortlists a student', async () => {
    const user = userEvent.setup()
    const calls: Array<{ method: string; body: unknown }> = []
    signedInAs(COMPANY, [
      {
        path: `/api/profiles/students/${STUDENT_ID}/shortlist`,
        status: 201,
        body: { shortlisted: true },
        onCall: (call) => calls.push(call),
      },
      {
        path: '/api/profiles/students',
        body: { count: 1, next: null, previous: null, results: [makeCompanyProfile()] },
      },
    ])
    renderApp('/company/students')

    await waitFor(() => expect(screen.getByRole('button', { name: /^shortlist$/i })).toBeInTheDocument())
    await user.click(screen.getByRole('button', { name: /^shortlist$/i }))

    await waitFor(() => expect(calls).toHaveLength(1))
    expect(calls[0].method).toBe('POST')
  })

  it('shows the verified badge that the placement cell set', async () => {
    signedInAs(COMPANY, [
      {
        path: '/api/profiles/students',
        body: {
          count: 1,
          next: null,
          previous: null,
          results: [makeCompanyProfile({ is_verified: true })],
        },
      },
    ])
    renderApp('/company/students')

    await waitFor(() => expect(screen.getByText('Verified')).toBeInTheDocument())
  })
})

describe('company student detail', () => {
  it('withholds contact details on an unverified profile', async () => {
    signedInAs(COMPANY, [
      { path: `/api/profiles/students/${STUDENT_ID}`, body: makeCompanyProfile() },
    ])
    renderApp(`/company/students/${STUDENT_ID}`)

    await waitFor(() => expect(screen.getByText('Contact')).toBeInTheDocument())
    expect(screen.getByText(/appear once this profile is verified/i)).toBeInTheDocument()
  })

  it('shows contact details once the profile is verified', async () => {
    signedInAs(COMPANY, [
      {
        path: `/api/profiles/students/${STUDENT_ID}`,
        body: makeCompanyProfile({
          is_verified: true,
          contact: { email: 'aarav.mehta@college.edu', phone: '9820011001' },
        }),
      },
    ])
    renderApp(`/company/students/${STUDENT_ID}`)

    await waitFor(() => expect(screen.getByText('9820011001')).toBeInTheDocument())
  })

  it('explains a profile the company is not allowed to see', async () => {
    signedInAs(COMPANY, [
      { path: `/api/profiles/students/${STUDENT_ID}`, status: 404, body: { detail: 'Not found.' } },
    ])
    renderApp(`/company/students/${STUDENT_ID}`)

    await waitFor(() =>
      expect(screen.getByText(/not visible to you/i)).toBeInTheDocument(),
    )
  })
})

describe('admin profile verification', () => {
  const UNVERIFIED = makeOwnProfile({ completion_percent: 71 })

  it('shows the completion aggregates behind the PRD metric', async () => {
    signedInAs(ADMIN, [
      {
        path: '/api/profiles/admin/stats',
        body: {
          profiles: 10,
          verified: 4,
          with_resume: 7,
          fully_complete: 2,
          average_completion_percent: 63,
          visibility: { all: 8, hidden: 2 },
        },
      },
      {
        path: '/api/profiles/admin',
        body: { count: 1, next: null, previous: null, results: [UNVERIFIED] },
      },
    ])
    renderApp('/admin/profiles')

    await waitFor(() => expect(screen.getByText('Avg. completion')).toBeInTheDocument())
    expect(screen.getByText('63%')).toBeInTheDocument()
    expect(screen.getByText('10')).toBeInTheDocument()
  })

  it('marks a profile verified', async () => {
    const user = userEvent.setup()
    const calls: Array<{ method: string; body: unknown }> = []
    signedInAs(ADMIN, [
      {
        path: `/api/profiles/admin/${STUDENT_ID}/verification`,
        body: makeOwnProfile({ is_verified: true }),
        onCall: (call) => calls.push(call),
      },
      {
        path: '/api/profiles/admin/stats',
        body: {
          profiles: 1,
          verified: 0,
          with_resume: 0,
          fully_complete: 0,
          average_completion_percent: 71,
          visibility: { all: 1 },
        },
      },
      {
        path: '/api/profiles/admin',
        body: { count: 1, next: null, previous: null, results: [UNVERIFIED] },
      },
    ])
    renderApp('/admin/profiles')

    await waitFor(() => expect(screen.getByRole('button', { name: /mark verified/i })).toBeInTheDocument())
    await user.click(screen.getByRole('button', { name: /mark verified/i }))

    await waitFor(() => expect(calls).toHaveLength(1))
    expect(calls[0].body).toEqual({ is_verified: true, note: '' })
  })

  it('shows each profile visibility so the admin knows who companies can see', async () => {
    signedInAs(ADMIN, [
      {
        path: '/api/profiles/admin/stats',
        body: {
          profiles: 1,
          verified: 0,
          with_resume: 0,
          fully_complete: 0,
          average_completion_percent: 0,
          visibility: { hidden: 1 },
        },
      },
      {
        path: '/api/profiles/admin',
        body: {
          count: 1,
          next: null,
          previous: null,
          results: [makeOwnProfile({ visibility: 'hidden' })],
        },
      },
    ])
    renderApp('/admin/profiles')

    await waitFor(() => expect(screen.getByText('hidden')).toBeInTheDocument())
  })
})
