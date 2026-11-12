import '@testing-library/jest-dom/vitest'
import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { makeCompanyProfile, makeOwnProfile } from '@/test/fixtures'
import { HEALTHY, makeUser, mockApi, renderApp, type Route } from '@/test/harness'
import {
  LEAKED_FIELDS,
  makeAnalysis,
  makeMatchResult,
  makeMatchScore,
  makeRegexAnalysis,
  PENDING_ANALYSIS,
  RESUME_FACTS,
  sequenced,
} from '@/test/intelligence-fixtures'

type Call = { method: string; body: unknown }

const UPLOADED = makeOwnProfile({
  resume_filename: 'aarav_mehta_backend.pdf',
  resume_uploaded_at: '2026-10-19T10:00:00Z',
  experience_years: '1.0',
  education_level: 'UG',
  parsed_experience_years: '1.0',
  parsed_education_levels: ['UG'],
})

const ANALYZE = '/api/profiles/me/resume/analyze'
const ANALYSIS = '/api/profiles/me/resume/analysis'

function signedInAsStudent(extra: Route[] = []) {
  localStorage.setItem('pcp.access', 'access-token')
  return mockApi([HEALTHY, { path: '/api/auth/me', body: makeUser() }, ...extra])
}

/** Every request to `path`, in order. */
function callsTo(fetchMock: ReturnType<typeof mockApi>, path: string, method = 'GET') {
  return fetchMock.mock.calls.filter(
    ([url, init]) => String(url).startsWith(path) && (init?.method ?? 'GET') === method,
  )
}

async function uploadResume(user: ReturnType<typeof userEvent.setup>) {
  await waitFor(() => expect(screen.getByLabelText(/upload resume/i)).toBeInTheDocument())
  await user.upload(
    screen.getByLabelText(/upload resume/i),
    new File(['%PDF-1.4'], 'aarav_mehta_backend.pdf', { type: 'application/pdf' }),
  )
}

const UPLOAD_ROUTE: Route = {
  path: '/api/profiles/me/resume',
  method: 'POST',
  status: 201,
  body: {
    suggestion: { experience_years: 1, education_level: 'UG', applied: true },
    analysis: PENDING_ANALYSIS,
    profile: UPLOADED,
  },
}

beforeEach(() => localStorage.clear())
afterEach(() => {
  vi.useRealTimers()
  vi.unstubAllGlobals()
  localStorage.clear()
})

describe('resume analysis after upload', () => {
  it('analyses the upload and shows the AI reading beside the pattern reading', async () => {
    const user = userEvent.setup()
    const fetchMock = signedInAsStudent([
      { path: ANALYZE, method: 'POST', body: makeAnalysis() },
      UPLOAD_ROUTE,
      sequenced({ path: '/api/profiles/me', method: 'GET' }, [makeOwnProfile(), UPLOADED]),
    ])
    renderApp('/student/profile')
    await uploadResume(user)

    await waitFor(() =>
      expect(screen.getByText('Read by the AI model (llama3.1:8b)')).toBeInTheDocument(),
    )
    expect(callsTo(fetchMock, ANALYZE, 'POST')).toHaveLength(1)
    // The upload said pending; the analyze call answers when it is done, so nothing polls.
    expect(callsTo(fetchMock, ANALYSIS)).toHaveLength(0)

    const table = screen.getByRole('table', { name: /values read from your resume/i })
    expect(within(table).getByRole('columnheader', { name: 'AI reading' })).toBeInTheDocument()
    expect(within(table).getByRole('columnheader', { name: 'Pattern reading' })).toBeInTheDocument()
    const experience = within(table).getByRole('row', { name: /experience/i })
    expect(within(experience).getByText('1.5 years')).toBeInTheDocument()
    expect(within(experience).getByText('1 year')).toBeInTheDocument()
    expect(within(experience).getByText('Agree')).toBeInTheDocument()
    expect(screen.getByText('Resume analysis finished.')).toBeInTheDocument()
  })

  it('says where the two readings differ', async () => {
    signedInAsStudent([
      {
        path: ANALYSIS,
        body: makeAnalysis({
          agreement: {
            experience_years: { regex: 4, llm: 1.5, agree: false },
            education_level: { regex: 'UG', llm: 'UG', agree: true },
          },
        }),
      },
      { path: '/api/profiles/me', body: UPLOADED },
    ])
    renderApp('/student/profile')

    await waitFor(() => expect(screen.getByText('Differ')).toBeInTheDocument())
    expect(screen.getByText(/the two readings differ/i)).toBeInTheDocument()
  })

  it('waits for a reading still in progress when the page opens, and stops once it is done', async () => {
    // The page was left mid-read: the server finishes it, so this page polls
    // rather than asking for a second reading.
    vi.useFakeTimers({ shouldAdvanceTime: true })
    const fetchMock = signedInAsStudent([
      { path: ANALYZE, method: 'POST', body: makeAnalysis() },
      sequenced({ path: ANALYSIS }, [PENDING_ANALYSIS, PENDING_ANALYSIS, makeAnalysis()]),
      { path: '/api/profiles/me', body: UPLOADED },
    ])
    renderApp('/student/profile')

    await waitFor(() => expect(screen.getByText(/^Analysing…/)).toBeInTheDocument())
    expect(callsTo(fetchMock, ANALYSIS)).toHaveLength(1)

    await vi.advanceTimersByTimeAsync(1000)
    await waitFor(() => expect(callsTo(fetchMock, ANALYSIS)).toHaveLength(2))
    expect(screen.getByText(/^Analysing…/)).toBeInTheDocument()

    await vi.advanceTimersByTimeAsync(2000)
    await waitFor(() =>
      expect(screen.getByText('Read by the AI model (llama3.1:8b)')).toBeInTheDocument(),
    )
    expect(callsTo(fetchMock, ANALYSIS)).toHaveLength(3)

    await vi.advanceTimersByTimeAsync(30_000)
    expect(callsTo(fetchMock, ANALYSIS)).toHaveLength(3)
    expect(callsTo(fetchMock, ANALYZE, 'POST')).toHaveLength(0)
  })

  it('stops polling after a bounded number of tries and then asks for the reading itself', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime })
    const fetchMock = signedInAsStudent([
      { path: ANALYZE, method: 'POST', body: makeAnalysis() },
      { path: ANALYSIS, body: PENDING_ANALYSIS },
      { path: '/api/profiles/me', body: UPLOADED },
    ])
    renderApp('/student/profile')
    await waitFor(() => expect(callsTo(fetchMock, ANALYSIS)).toHaveLength(1))

    for (const delay of [1000, 2000, 4000, 8000, 8000]) {
      const before = callsTo(fetchMock, ANALYSIS).length
      await vi.advanceTimersByTimeAsync(delay)
      await waitFor(() => expect(callsTo(fetchMock, ANALYSIS)).toHaveLength(before + 1))
    }

    await waitFor(() => expect(screen.getByText(/taking longer than usual/i)).toBeInTheDocument())
    await vi.advanceTimersByTimeAsync(60_000)
    // The mount read plus five polls, and no more.
    expect(callsTo(fetchMock, ANALYSIS)).toHaveLength(6)
    expect(callsTo(fetchMock, ANALYZE, 'POST')).toHaveLength(0)

    // Nothing is going to finish it, so "Check again" runs the reading.
    await user.click(screen.getByRole('button', { name: 'Check again' }))
    await waitFor(() =>
      expect(screen.getByText('Read by the AI model (llama3.1:8b)')).toBeInTheDocument(),
    )
    expect(callsTo(fetchMock, ANALYZE, 'POST')).toHaveLength(1)
    expect(callsTo(fetchMock, ANALYSIS)).toHaveLength(6)
  })

  it('leaves no poll timer behind when the page closes mid-poll', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    const fetchMock = signedInAsStudent([
      { path: ANALYSIS, body: PENDING_ANALYSIS },
      { path: '/api/profiles/me', body: UPLOADED },
    ])
    const { unmount } = renderApp('/student/profile')
    await waitFor(() =>
      expect(screen.getByText('Analysing… still reading your resume.')).toBeInTheDocument(),
    )
    expect(callsTo(fetchMock, ANALYSIS)).toHaveLength(1)

    unmount()
    expect(vi.getTimerCount()).toBe(0)
    await vi.advanceTimersByTimeAsync(30_000)
    expect(callsTo(fetchMock, ANALYSIS)).toHaveLength(1)
  })

  it.each([
    ['failed', /the full reading did not finish/i, 'Try again'],
    ['skipped', /no text could be read from this resume/i, null],
  ] as const)('shows a %s reading after the upload without polling', async (status, message, retry) => {
    const user = userEvent.setup()
    const fetchMock = signedInAsStudent([
      {
        path: ANALYZE,
        method: 'POST',
        body: makeAnalysis({ status, source: null, model_name: null, suggested_skills: [], suggested_experience: [] }),
      },
      UPLOAD_ROUTE,
      sequenced({ path: '/api/profiles/me', method: 'GET' }, [makeOwnProfile(), UPLOADED]),
    ])
    renderApp('/student/profile')
    await uploadResume(user)

    await waitFor(() => expect(screen.getByText(message)).toBeInTheDocument())
    if (retry) expect(screen.getByRole('button', { name: retry })).toBeInTheDocument()
    expect(callsTo(fetchMock, ANALYZE, 'POST')).toHaveLength(1)
    expect(callsTo(fetchMock, ANALYSIS)).toHaveLength(0)
  })

  it('offers the AI reading again when the reading fell back to regex', async () => {
    const user = userEvent.setup()
    const calls: Call[] = []
    signedInAsStudent([
      {
        path: ANALYZE,
        method: 'POST',
        body: makeAnalysis({ suggested_skills: [], suggested_experience: [] }),
        onCall: (call) => calls.push(call),
      },
      { path: ANALYSIS, body: makeRegexAnalysis() },
      { path: '/api/profiles/me', body: UPLOADED },
    ])
    renderApp('/student/profile')

    await waitFor(() =>
      expect(screen.getByText('Read by pattern matching (regex)')).toBeInTheDocument(),
    )
    // No model reading, so there is nothing to put beside the pattern one.
    expect(screen.queryByRole('columnheader', { name: 'AI reading' })).not.toBeInTheDocument()
    expect(calls).toHaveLength(0)

    await user.click(screen.getByRole('button', { name: 'Try the AI reading again' }))

    await waitFor(() =>
      expect(screen.getByText('Read by the AI model (llama3.1:8b)')).toBeInTheDocument(),
    )
    expect(calls).toHaveLength(1)
    expect(screen.queryByRole('button', { name: 'Try the AI reading again' })).not.toBeInTheDocument()
  })

  it('does not offer the retry when the model read the resume', async () => {
    signedInAsStudent([
      { path: ANALYSIS, body: makeAnalysis() },
      { path: '/api/profiles/me', body: UPLOADED },
    ])
    renderApp('/student/profile')

    await waitFor(() =>
      expect(screen.getByText('Read by the AI model (llama3.1:8b)')).toBeInTheDocument(),
    )
    expect(screen.queryByRole('button', { name: 'Try the AI reading again' })).not.toBeInTheDocument()
  })

  it('says when the matcher has been used too often', async () => {
    const user = userEvent.setup()
    signedInAsStudent([
      {
        path: ANALYZE,
        method: 'POST',
        status: 429,
        body: { detail: 'Request was throttled. Expected available in 120 seconds.' },
      },
      UPLOAD_ROUTE,
      { path: '/api/profiles/me', method: 'GET', body: makeOwnProfile() },
    ])
    renderApp('/student/profile')
    await uploadResume(user)

    await waitFor(() =>
      expect(screen.getByRole('alert')).toHaveTextContent(/too many times.*about 2 minutes/i),
    )
  })
})

describe('resume suggestions', () => {
  it('adds a suggested skill only when the student clicks it', async () => {
    const user = userEvent.setup()
    const calls: Call[] = []
    signedInAsStudent([
      { path: ANALYSIS, body: makeAnalysis({ suggested_experience: [] }) },
      {
        path: '/api/profiles/me/skills',
        method: 'POST',
        status: 201,
        body: { id: 's-9', name: 'Docker', slug: 'docker', category: 'technical' },
        onCall: (call) => calls.push(call),
      },
      { path: '/api/profiles/me', body: UPLOADED },
    ])
    renderApp('/student/profile')

    const suggested = await screen.findByRole('list', { name: 'Suggested skills' })
    expect(within(suggested).getByRole('button', { name: 'Add Docker' })).toBeInTheDocument()
    expect(calls).toHaveLength(0)

    await user.click(within(suggested).getByRole('button', { name: 'Add Docker' }))

    await waitFor(() => expect(calls).toHaveLength(1))
    expect(calls[0].body).toEqual({ name: 'Docker', category: 'technical' })
    await waitFor(() => expect(screen.getByText('Added Docker to your skills.')).toBeInTheDocument())
    expect(within(suggested).queryByRole('button', { name: 'Add Docker' })).not.toBeInTheDocument()
    expect(within(suggested).getByRole('button', { name: 'Add PostgreSQL' })).toBeInTheDocument()
  })

  it('asks for the kind of role before adding an experience the resume gave no kind for', async () => {
    const user = userEvent.setup()
    const calls: Call[] = []
    signedInAsStudent([
      {
        path: ANALYSIS,
        body: makeAnalysis({
          suggested_skills: [],
          suggested_experience: [
            {
              role: 'Data Analyst',
              organization: 'Arcadia Retail',
              start_date: '2024-01-01',
              end_date: null,
              description: '',
            },
          ],
        }),
      },
      {
        path: '/api/profiles/me/experience',
        method: 'POST',
        status: 201,
        body: {},
        onCall: (call) => calls.push(call),
      },
      { path: '/api/profiles/me', body: UPLOADED },
    ])
    renderApp('/student/profile')

    const suggested = await screen.findByRole('list', { name: 'Suggested experience' })
    const kind = within(suggested).getByLabelText('Kind of role')
    // Not silently defaulted to anything.
    expect(kind).toHaveValue('')

    await user.click(within(suggested).getByRole('button', { name: 'Add to my experience' }))
    expect(within(suggested).getByRole('alert')).toHaveTextContent(/choose what kind of role/i)
    expect(kind).toHaveAttribute('aria-invalid', 'true')
    expect(calls).toHaveLength(0)

    await user.selectOptions(kind, 'full_time')
    await user.click(within(suggested).getByRole('button', { name: 'Add to my experience' }))

    await waitFor(() => expect(calls).toHaveLength(1))
    expect(calls[0].body).toEqual({
      role: 'Data Analyst',
      organization: 'Arcadia Retail',
      kind: 'full_time',
      start_date: '2024-01-01',
      end_date: null,
      description: '',
    })
    await waitFor(() =>
      expect(screen.getByText('Added Data Analyst to your experience.')).toBeInTheDocument(),
    )
  })

  it('keeps the kind the resume did give, and still waits for the click', async () => {
    const user = userEvent.setup()
    const calls: Call[] = []
    signedInAsStudent([
      { path: ANALYSIS, body: makeAnalysis({ suggested_skills: [] }) },
      {
        path: '/api/profiles/me/experience',
        method: 'POST',
        status: 201,
        body: {},
        onCall: (call) => calls.push(call),
      },
      { path: '/api/profiles/me', body: UPLOADED },
    ])
    renderApp('/student/profile')

    const suggested = await screen.findByRole('list', { name: 'Suggested experience' })
    expect(within(suggested).getByText('Software Intern at Loadstar Logistics')).toBeInTheDocument()
    expect(within(suggested).getByLabelText('Kind of role')).toHaveValue('internship')
    expect(calls).toHaveLength(0)

    await user.click(within(suggested).getByRole('button', { name: 'Add to my experience' }))
    await waitFor(() => expect(calls).toHaveLength(1))
    expect((calls[0].body as Record<string, string>).kind).toBe('internship')
  })
})

describe('resume analysis privacy', () => {
  it('keeps admin-only facts out of every student and company fixture', () => {
    const fixtures = [
      makeOwnProfile(),
      makeCompanyProfile(),
      makeAnalysis(),
      makeRegexAnalysis(),
      PENDING_ANALYSIS,
      makeMatchScore(),
      makeMatchResult(),
    ]
    for (const fixture of fixtures) {
      const keys = JSON.stringify(fixture)
      for (const field of ['"age"', '"date_of_birth"', '"resume_facts_admin"', '"verification_checks"', '"warning_count"']) {
        expect(keys).not.toContain(field)
      }
      expect(keys).not.toContain(RESUME_FACTS.date_of_birth)
    }
  })

  it('never renders age, date of birth or the resume CGPA, even if a payload carried them', async () => {
    signedInAsStudent([
      { path: ANALYSIS, body: { ...makeAnalysis(), ...LEAKED_FIELDS } },
      { path: '/api/profiles/me', body: { ...UPLOADED, ...LEAKED_FIELDS } },
    ])
    renderApp('/student/profile')

    await waitFor(() =>
      expect(screen.getByText('Read by the AI model (llama3.1:8b)')).toBeInTheDocument(),
    )
    const page = document.body.textContent ?? ''
    expect(page).not.toContain(RESUME_FACTS.date_of_birth)
    expect(page).not.toContain(String(RESUME_FACTS.cgpa))
    expect(page).not.toMatch(/date of birth|\bage\b|for verification only/i)
    expect(page).not.toContain(RESUME_FACTS.phones[0])
    expect(page).not.toContain(RESUME_FACTS.emails[0])
  })
})
