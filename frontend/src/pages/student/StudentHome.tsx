import { useEffect, useState, type FormEvent } from 'react'
import { Link } from 'react-router-dom'

import { ApiError } from '@/api/client'
import { describeMatchingError, JD_MIN_CHARS } from '@/api/matching'
import { profilesApi, type OwnMatch, type OwnProfile } from '@/api/profiles'
import { MatchBreakdown, ScoreBar, SkillChips } from '@/components/MatchDisplay'
import { Alert, Badge, Button, Card, CardTitle, PageHeader } from '@/components/ui'
import { useAuth } from '@/auth/AuthContext'

const VISIBILITY_LABEL: Record<string, string> = {
  all: 'Visible to all companies',
  shortlisted: 'Visible to companies that shortlisted you',
  hidden: 'Hidden from companies',
}

export default function StudentHome() {
  const { user } = useAuth()
  const [profile, setProfile] = useState<OwnProfile | null>(null)
  const [loaded, setLoaded] = useState(false)

  useEffect(() => {
    let cancelled = false
    profilesApi
      .me()
      .then((next) => !cancelled && setProfile(next))
      .catch(() => !cancelled && setProfile(null))
      .finally(() => !cancelled && setLoaded(true))
    return () => {
      cancelled = true
    }
  }, [])

  return (
    <>
      <PageHeader
        title={`Hello, ${user?.full_name || 'student'}`}
        subtitle="Your profile is what companies see. Keep it current."
      />

      {/* Shown until onboarding is completed, even after "Skip for now". */}
      {profile && !profile.onboarding_completed ? (
        <div className="mb-4">
          <Alert tone="info" title="Finish setting up your account">
            <p>
              Your phone number and career plans are still missing.{' '}
              <Link to="/student/onboarding" className="font-medium underline">
                Complete the short form
              </Link>
            </p>
          </Alert>
        </div>
      ) : null}

      <div className="grid gap-4 sm:grid-cols-2">
        <Link to="/student/profile" className="block transition hover:opacity-80">
          <Card>
            <CardTitle hint="Experience, projects, skills and your resume.">My profile</CardTitle>
            <p className="text-3xl font-semibold tabular-nums">
              {profile ? `${profile.completion_percent}%` : '—'}
            </p>
            <p className="text-sm text-ink-600">complete</p>
            {profile ? (
              <p className="mt-3">
                <Badge tone={profile.is_verified ? 'success' : 'neutral'}>
                  {profile.is_verified ? 'Verified' : 'Not yet verified'}
                </Badge>
              </p>
            ) : null}
          </Card>
        </Link>

        <Card>
          <CardTitle hint="Anchored to your PRN on the placement cell's roster.">
            Your identity
          </CardTitle>
          <dl className="space-y-2 text-sm">
            <div className="flex justify-between gap-4">
              <dt className="text-ink-600">PRN</dt>
              <dd className="font-mono">{user?.prn}</dd>
            </div>
            <div className="flex justify-between gap-4">
              <dt className="text-ink-600">College email</dt>
              <dd>{user?.email}</dd>
            </div>
            {profile ? (
              <div className="flex justify-between gap-4">
                <dt className="text-ink-600">Visibility</dt>
                <dd className="text-right">{VISIBILITY_LABEL[profile.visibility]}</dd>
              </div>
            ) : null}
          </dl>
        </Card>

        {loaded && profile ? <RolesCard categories={profile.categories ?? []} /> : null}
      </div>

      <div className="mt-4">
        <FitCheckCard />
      </div>
    </>
  )
}

function RolesCard({ categories }: { categories: string[] }) {
  return (
    <Card className="sm:col-span-2">
      <CardTitle hint="Role categories come from the job descriptions recruiters post, matched against your profile and resume.">
        Roles you fit
      </CardTitle>
      {categories.length ? (
        <ul className="flex flex-wrap gap-2" aria-label="Roles you fit">
          {categories.map((name) => (
            <li key={name}>
              <Badge tone="brand">{name}</Badge>
            </li>
          ))}
        </ul>
      ) : (
        <p className="text-sm text-ink-600">
          No roles yet: categories appear as recruiters post job descriptions.
        </p>
      )}
    </Card>
  )
}

/**
 * The student's own match against a JD they paste. It is labelled a match,
 * never a probability, and the breakdown is always shown beside the number.
 */
function FitCheckCard() {
  const [jdText, setJdText] = useState('')
  const [busy, setBusy] = useState(false)
  const [result, setResult] = useState<OwnMatch | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [fieldError, setFieldError] = useState<string | null>(null)

  async function submit(event: FormEvent) {
    event.preventDefault()
    setError(null)
    setFieldError(null)
    if (jdText.trim().length < JD_MIN_CHARS) {
      setFieldError(`Paste at least ${JD_MIN_CHARS} characters of the job description.`)
      return
    }
    setBusy(true)
    try {
      setResult(await profilesApi.myMatch(jdText))
    } catch (caught) {
      const jdErrors = caught instanceof ApiError ? caught.fieldErrors.jd_text : undefined
      if (jdErrors?.length) setFieldError(jdErrors.join(' '))
      else setError(describeMatchingError(caught, 'Could not check your fit. Try again.'))
    } finally {
      setBusy(false)
    }
  }

  return (
    <Card>
      <CardTitle hint="Paste a job description to see how your profile and resume match it, and which skills it asks for that you have not listed.">
        Check my fit for a JD
      </CardTitle>

      <form onSubmit={submit} className="space-y-3" noValidate>
        <div className="space-y-1.5">
          <label htmlFor="fit-jd-text" className="block text-sm font-medium text-ink-800">
            Job description
          </label>
          <textarea
            id="fit-jd-text"
            rows={6}
            value={jdText}
            onChange={(event) => setJdText(event.target.value)}
            aria-invalid={fieldError ? true : undefined}
            aria-describedby={fieldError ? 'fit-jd-text-error' : 'fit-jd-text-hint'}
            placeholder="We are hiring a backend engineer with Python, Django and PostgreSQL…"
            className="w-full rounded-lg border border-ink-200 px-3 py-2.5 text-sm focus:border-brand-500 focus:ring-2 focus:ring-brand-500/30 focus:outline-none"
          />
          {fieldError ? (
            <p id="fit-jd-text-error" role="alert" className="text-sm text-bad-600">
              {fieldError}
            </p>
          ) : (
            <p id="fit-jd-text-hint" className="text-xs text-ink-400">
              Only you see this result.
            </p>
          )}
        </div>
        <Button type="submit" loading={busy}>
          Check my fit
        </Button>
      </form>

      <p role="status" aria-live="polite" className="sr-only">
        {busy ? 'Checking your fit…' : result ? `Match ${result.match.score} of 100.` : ''}
      </p>

      {error ? (
        <div className="mt-4">
          <Alert tone="error">{error}</Alert>
        </div>
      ) : null}

      {result ? (
        <div className="mt-5 space-y-4 border-t border-ink-100 pt-4">
          {result.job.canonical_role ? (
            <p className="text-sm text-ink-600">
              Read as a <strong>{result.job.canonical_role}</strong> role.
            </p>
          ) : null}
          <ScoreBar score={result.match.score} />
          <p className="text-xs text-ink-400">
            A match score, built from the parts below. It is a guide to where you stand, not a
            prediction of the outcome.
          </p>
          <MatchBreakdown match={result.match} />
          <SkillChips match={result.match} />
        </div>
      ) : null}
    </Card>
  )
}
