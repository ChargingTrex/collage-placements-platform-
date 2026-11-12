import '@testing-library/jest-dom/vitest'
import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { makeOwnProfile } from '@/test/fixtures'
import { HEALTHY, makeUser, mockApi, renderApp, type Route } from '@/test/harness'
import { JOB_SUMMARY, LEAKED_FIELDS, makeMatchScore, RESUME_FACTS } from '@/test/intelligence-fixtures'

const JD = 'Backend engineer: Python, Django and Docker, one year of experience building APIs.'
const MATCH = '/api/profiles/me/match'

function signedInAsStudent(extra: Route[] = []) {
  localStorage.setItem('pcp.access', 'access-token')
  return mockApi([HEALTHY, { path: '/api/auth/me', body: makeUser() }, ...extra])
}

async function checkFit(user: ReturnType<typeof userEvent.setup>, text = JD) {
  const box = await screen.findByLabelText('Job description')
  await user.click(box)
  await user.paste(text)
  await user.click(screen.getByRole('button', { name: 'Check my fit' }))
}

beforeEach(() => localStorage.clear())
afterEach(() => {
  vi.unstubAllGlobals()
  localStorage.clear()
})

describe('roles you fit', () => {
  it('lists the role categories the profile was sorted into', async () => {
    signedInAsStudent([
      {
        path: '/api/profiles/me',
        body: makeOwnProfile({ categories: ['Backend Engineer', 'Data Analyst'] }),
      },
    ])
    renderApp('/student')

    const roles = await screen.findByRole('list', { name: 'Roles you fit' })
    expect(within(roles).getByText('Backend Engineer')).toBeInTheDocument()
    expect(within(roles).getByText('Data Analyst')).toBeInTheDocument()
  })

  it('says honestly that there are no roles yet rather than inventing them', async () => {
    signedInAsStudent([{ path: '/api/profiles/me', body: makeOwnProfile({ categories: [] }) }])
    renderApp('/student')

    await waitFor(() =>
      expect(
        screen.getByText('No roles yet: categories appear as recruiters post job descriptions.'),
      ).toBeInTheDocument(),
    )
    expect(screen.queryByRole('list', { name: 'Roles you fit' })).not.toBeInTheDocument()
  })
})

describe('check my fit for a JD', () => {
  it('shows the match with its full breakdown, labelled a match and never a probability', async () => {
    const user = userEvent.setup()
    const calls: Array<{ method: string; body: unknown }> = []
    signedInAsStudent([
      {
        path: MATCH,
        method: 'POST',
        body: { match: makeMatchScore(), job: JOB_SUMMARY },
        onCall: (call) => calls.push(call),
      },
      { path: '/api/profiles/me', body: makeOwnProfile({ categories: [] }) },
    ])
    renderApp('/student')
    await checkFit(user)

    await waitFor(() => expect(screen.getByText('Match 72 of 100')).toBeInTheDocument())
    expect(calls[0].body).toEqual({ jd_text: JD })
    expect(screen.getByRole('meter', { name: 'Match' })).toHaveAttribute(
      'aria-valuetext',
      'Match 72 of 100',
    )

    // The breakdown is shown without asking for it: every part with its weight.
    const breakdown = screen.getByRole('table', { name: 'Match breakdown' })
    const expected: Array<[string, string, string]> = [
      ['Semantic', '80%', '45%'],
      ['Skills', '50%', '35%'],
      ['Experience', '100%', '10%'],
      ['Education', '100%', '10%'],
    ]
    for (const [part, score, weight] of expected) {
      const row = within(breakdown).getByRole('row', { name: new RegExp(`^${part}`) })
      expect(within(row).getByText(score)).toBeInTheDocument()
      expect(within(row).getByText(weight)).toBeInTheDocument()
    }

    const matched = screen.getByRole('list', { name: 'Matched skills' })
    expect(within(matched).getByText('Python')).toBeInTheDocument()
    expect(within(matched).getByText('Django')).toBeInTheDocument()
    expect(within(screen.getByRole('list', { name: 'Missing skills' })).getByText('Docker')).toBeInTheDocument()

    expect(document.body.textContent).not.toMatch(/probabilit/i)
  })

  it('marks a part the JD gave nothing to score as not counted', async () => {
    const user = userEvent.setup()
    signedInAsStudent([
      {
        path: MATCH,
        method: 'POST',
        body: {
          match: makeMatchScore({
            components: {
              semantic: { score: 0.6, weight: 0.6923, raw: 0.15 },
              skills: { score: 0, weight: 0 },
              experience: { score: 1, weight: 0.1538 },
              education: { score: 1, weight: 0.1538 },
            },
            matched_skills: [],
            missing_skills: [],
          }),
          job: { ...JOB_SUMMARY, required_skills: [] },
        },
      },
      { path: '/api/profiles/me', body: makeOwnProfile() },
    ])
    renderApp('/student')
    await checkFit(user)

    const breakdown = await screen.findByRole('table', { name: 'Match breakdown' })
    const skills = within(breakdown).getByRole('row', { name: /^Skills/ })
    expect(within(skills).getByText('not counted')).toBeInTheDocument()
    expect(screen.getByText(/names no skill we recognise/i)).toBeInTheDocument()
  })

  it('explains the hourly limit when the matcher answers 429', async () => {
    const user = userEvent.setup()
    signedInAsStudent([
      {
        path: MATCH,
        method: 'POST',
        status: 429,
        body: { detail: 'Request was throttled. Expected available in 1800 seconds.' },
      },
      { path: '/api/profiles/me', body: makeOwnProfile() },
    ])
    renderApp('/student')
    await checkFit(user)

    await waitFor(() =>
      expect(screen.getByRole('alert')).toHaveTextContent(
        'You have run the matcher too many times in the last hour. Try again in about 30 minutes.',
      ),
    )
    expect(screen.queryByText(/match \d+ of 100/i)).not.toBeInTheDocument()
  })

  it('shows the server validation message against the job description', async () => {
    const user = userEvent.setup()
    signedInAsStudent([
      {
        path: MATCH,
        method: 'POST',
        status: 400,
        body: { jd_text: ['Ensure this field has no more than 20000 characters.'] },
      },
      { path: '/api/profiles/me', body: makeOwnProfile() },
    ])
    renderApp('/student')
    await checkFit(user)

    await waitFor(() =>
      expect(screen.getByText('Ensure this field has no more than 20000 characters.')).toBeInTheDocument(),
    )
    expect(screen.getByLabelText('Job description')).toHaveAttribute('aria-invalid', 'true')
  })

  it('asks for more of the JD before calling the server', async () => {
    const user = userEvent.setup()
    const calls: Array<{ method: string; body: unknown }> = []
    signedInAsStudent([
      { path: MATCH, method: 'POST', body: {}, onCall: (call) => calls.push(call) },
      { path: '/api/profiles/me', body: makeOwnProfile() },
    ])
    renderApp('/student')
    await checkFit(user, 'Python dev')

    // Announced, not just painted red, and tied to the field it is about.
    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent('Paste at least 30 characters of the job description.')
    const box = screen.getByLabelText('Job description')
    expect(box).toHaveAttribute('aria-invalid', 'true')
    expect(box).toHaveAttribute('aria-describedby', alert.id)
    expect(calls).toHaveLength(0)
  })

  it('never renders age, date of birth or the resume CGPA from the student payloads', async () => {
    const user = userEvent.setup()
    signedInAsStudent([
      {
        path: MATCH,
        method: 'POST',
        body: { match: { ...makeMatchScore(), ...LEAKED_FIELDS }, job: JOB_SUMMARY, ...LEAKED_FIELDS },
      },
      {
        path: '/api/profiles/me',
        body: { ...makeOwnProfile({ categories: ['Backend Engineer'] }), ...LEAKED_FIELDS },
      },
    ])
    renderApp('/student')
    await checkFit(user)

    await waitFor(() => expect(screen.getByText('Match 72 of 100')).toBeInTheDocument())
    const page = document.body.textContent ?? ''
    expect(page).not.toContain(RESUME_FACTS.date_of_birth)
    expect(page).not.toContain(String(RESUME_FACTS.cgpa))
    expect(page).not.toMatch(/date of birth|\bage\b/i)
  })
})
