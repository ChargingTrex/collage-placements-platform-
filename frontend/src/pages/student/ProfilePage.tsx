import { useCallback, useEffect, useState, type FormEvent } from 'react'

import { ApiError } from '@/api/client'
import { profilesApi, type OwnProfile, type Visibility } from '@/api/profiles'
import { Alert, Badge, Button, Card, CardTitle, Field, PageHeader } from '@/components/ui'
import CareerPathCard from '@/pages/student/CareerPathCard'
import ExperienceCard from '@/pages/student/ExperienceCard'
import ProjectsCard from '@/pages/student/ProjectsCard'
import ResumeCard from '@/pages/student/ResumeCard'
import SkillsCard from '@/pages/student/SkillsCard'
import TranscriptCard from '@/pages/student/TranscriptCard'
import CgpaCard from '@/pages/student/CgpaCard'
import MarksheetsCard from '@/pages/student/MarksheetsCard'

const COMPLETION_LABELS: Record<string, string> = {
  headline: 'A one-line headline',
  summary: 'A summary',
  skills: 'At least three skills',
  experience: 'At least one experience entry',
  projects: 'At least one project',
  resume: 'A resume upload',
  links: 'At least one link',
  career_path: 'A career path',
}

function visibilityOptions(
  shortlistedBy: number,
): Array<{ value: Visibility; label: string; hint: string }> {
  const companies = `${shortlistedBy} compan${shortlistedBy === 1 ? 'y has' : 'ies have'}`
  return [
    {
      value: 'all',
      label: 'All companies',
      hint: 'Every recruiter with an account can find your profile.',
    },
    {
      value: 'shortlisted',
      label: 'Shortlisted companies only',
      // The count is the point: with nobody shortlisted this setting shows
      // the profile to no one, and the student has no other way to know.
      hint:
        shortlistedBy === 0
          ? 'No company has shortlisted you yet, so this hides your profile from everyone.'
          : `${companies} shortlisted you. Only they would see your profile.`,
    },
    {
      value: 'hidden',
      label: 'Hidden',
      hint: 'No company can see your profile. The placement cell still can.',
    },
  ]
}

export default function ProfilePage() {
  const [profile, setProfile] = useState<OwnProfile | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)

  const reload = useCallback(async () => {
    try {
      setProfile(await profilesApi.me())
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : 'Could not load your profile.')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void reload()
  }, [reload])

  if (loading) return <p className="py-16 text-center text-sm text-ink-400">Loading your profile…</p>
  if (!profile) return <Alert tone="error">{error ?? 'Profile unavailable.'}</Alert>

  return (
    <>
      <PageHeader
        title="My profile"
        subtitle="This is what companies see. Your name, department, batch and CGPA come from the placement cell's roster."
      />

      {error ? (
        <div className="mb-4">
          <Alert tone="error">{error}</Alert>
        </div>
      ) : null}

      <div className="grid gap-6 lg:grid-cols-3">
        <div className="space-y-6 lg:col-span-2">
          <BasicsCard profile={profile} onProfile={setProfile} />
          <CareerPathCard profile={profile} onProfile={setProfile} />
          <ResumeCard profile={profile} onProfile={setProfile} />
          <TranscriptCard profile={profile} onProfile={setProfile} />
          <CgpaCard profile={profile} onProfile={setProfile} />
          <MarksheetsCard profile={profile} onProfile={setProfile} />
          <SkillsCard skills={profile.skills} onChanged={reload} />
          <ExperienceCard entries={profile.experience_entries} onChanged={reload} />
          <ProjectsCard projects={profile.projects} onChanged={reload} />
        </div>

        <div className="space-y-6">
          <CompletionCard profile={profile} />
          <VisibilityCard profile={profile} onProfile={setProfile} />
          <RosterCard profile={profile} />
        </div>
      </div>
    </>
  )
}

function BasicsCard({
  profile,
  onProfile,
}: {
  profile: OwnProfile
  onProfile: (profile: OwnProfile) => void
}) {
  const [draft, setDraft] = useState({
    headline: profile.headline,
    summary: profile.summary,
    phone: profile.phone,
    github_url: profile.github_url,
    linkedin_url: profile.linkedin_url,
    website_url: profile.website_url,
  })
  const [busy, setBusy] = useState(false)
  const [saved, setSaved] = useState(false)
  const [error, setError] = useState<ApiError | null>(null)

  async function save(event: FormEvent) {
    event.preventDefault()
    setBusy(true)
    setError(null)
    setSaved(false)
    try {
      onProfile(await profilesApi.updateMe(draft))
      setSaved(true)
    } catch (caught) {
      setError(caught instanceof ApiError ? caught : new ApiError(0, 'Could not save.'))
    } finally {
      setBusy(false)
    }
  }

  const set = (field: keyof typeof draft) => (event: { target: { value: string } }) => {
    setSaved(false)
    setDraft((current) => ({ ...current, [field]: event.target.value }))
  }

  return (
    <Card>
      <CardTitle hint="The first thing a recruiter reads.">About you</CardTitle>

      <form onSubmit={save} className="space-y-4">
        {error && !Object.keys(error.fieldErrors).length ? (
          <Alert tone="error">{error.message}</Alert>
        ) : null}

        <Field
          label="Headline"
          name="headline"
          value={draft.headline}
          onChange={set('headline')}
          placeholder="Backend developer"
          errors={error?.fieldErrors.headline}
        />

        <div className="space-y-1.5">
          <label htmlFor="summary" className="block text-sm font-medium text-ink-800">
            Summary
          </label>
          <textarea
            id="summary"
            rows={4}
            value={draft.summary}
            onChange={set('summary')}
            placeholder="A few sentences on what you build and what you want to work on."
            className="w-full rounded-lg border border-ink-200 px-3 py-2.5 text-sm focus:border-brand-500 focus:ring-2 focus:ring-brand-500/30 focus:outline-none"
          />
        </div>

        <div className="grid gap-3 sm:grid-cols-2">
          <Field label="Phone" name="phone" value={draft.phone} onChange={set('phone')} />
          <Field
            label="GitHub"
            name="github_url"
            type="url"
            placeholder="https://github.com/…"
            value={draft.github_url}
            onChange={set('github_url')}
            errors={error?.fieldErrors.github_url}
          />
          <Field
            label="LinkedIn"
            name="linkedin_url"
            type="url"
            placeholder="https://linkedin.com/in/…"
            value={draft.linkedin_url}
            onChange={set('linkedin_url')}
            errors={error?.fieldErrors.linkedin_url}
          />
          <Field
            label="Website"
            name="website_url"
            type="url"
            placeholder="https://"
            value={draft.website_url}
            onChange={set('website_url')}
            errors={error?.fieldErrors.website_url}
          />
        </div>

        <div className="flex items-center gap-3">
          <Button type="submit" loading={busy}>
            Save
          </Button>
          {saved ? <span className="text-sm text-ok-600">Saved.</span> : null}
        </div>
      </form>
    </Card>
  )
}

function CompletionCard({ profile }: { profile: OwnProfile }) {
  const entries = Object.entries(profile.completion_detail ?? {})
  const done = entries.filter(([, value]) => value).length

  return (
    <Card>
      <CardTitle>Profile completion</CardTitle>

      <div className="flex items-baseline gap-2">
        <p className="text-3xl font-semibold tabular-nums">{profile.completion_percent}%</p>
        <p className="text-sm text-ink-600">
          {done} of {entries.length} done
        </p>
      </div>

      <div
        className="mt-3 h-2 overflow-hidden rounded-full bg-ink-100"
        role="progressbar"
        aria-valuenow={profile.completion_percent}
        aria-valuemin={0}
        aria-valuemax={100}
      >
        <div
          className="h-full rounded-full bg-brand-600 transition-[width]"
          style={{ width: `${profile.completion_percent}%` }}
        />
      </div>

      <ul className="mt-4 space-y-1.5 text-sm">
        {entries.map(([key, value]) => (
          <li key={key} className="flex items-center gap-2">
            <span className={value ? 'text-ok-600' : 'text-ink-200'} aria-hidden>
              {value ? '●' : '○'}
            </span>
            <span className={value ? 'text-ink-400 line-through' : 'text-ink-800'}>
              {COMPLETION_LABELS[key] ?? key}
            </span>
          </li>
        ))}
      </ul>
    </Card>
  )
}

function VisibilityCard({
  profile,
  onProfile,
}: {
  profile: OwnProfile
  onProfile: (profile: OwnProfile) => void
}) {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function choose(visibility: Visibility) {
    if (visibility === profile.visibility) return
    setBusy(true)
    setError(null)
    try {
      await profilesApi.setVisibility(visibility)
      onProfile(await profilesApi.me())
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : 'Could not change visibility.')
    } finally {
      setBusy(false)
    }
  }

  // "Shortlisted only" with nobody shortlisted shows the profile to no one,
  // which looks identical to being visible from the student's side.
  const invisible =
    profile.visibility === 'hidden' ||
    (profile.visibility === 'shortlisted' && profile.shortlisted_by_count === 0)

  return (
    <Card>
      <CardTitle hint="Enforced on the server, not just hidden in the page.">
        Who can see this
      </CardTitle>

      {error ? (
        <div className="mb-3">
          <Alert tone="error">{error}</Alert>
        </div>
      ) : null}

      {invisible ? (
        <div className="mb-3">
          <Alert tone="warning" title="No company can see your profile right now">
            {profile.visibility === 'shortlisted' ? (
              <p>
                You have chosen to be visible only to companies that shortlisted you, and none
                have yet. A company has to be able to see your profile before it can shortlist
                you, so nobody can find you while this is set.
              </p>
            ) : (
              <p>Your profile is hidden from every company.</p>
            )}
            <Button
              size="sm"
              className="mt-3"
              loading={busy}
              onClick={() => choose('all')}
            >
              Make my profile visible to all companies
            </Button>
          </Alert>
        </div>
      ) : null}

      <fieldset disabled={busy} className="space-y-2">
        <legend className="sr-only">Profile visibility</legend>
        {visibilityOptions(profile.shortlisted_by_count).map((option) => (
          <label
            key={option.value}
            className={`flex cursor-pointer gap-3 rounded-lg border p-3 transition ${
              profile.visibility === option.value
                ? 'border-brand-500 bg-brand-50'
                : 'border-ink-200 hover:bg-ink-50'
            }`}
          >
            <input
              type="radio"
              name="visibility"
              className="mt-1"
              checked={profile.visibility === option.value}
              onChange={() => choose(option.value)}
            />
            <span>
              <span className="block text-sm font-medium">{option.label}</span>
              <span className="block text-xs text-ink-600">{option.hint}</span>
            </span>
          </label>
        ))}
      </fieldset>
    </Card>
  )
}

function RosterCard({ profile }: { profile: OwnProfile }) {
  const facts: Array<[string, string]> = [
    ['PRN', profile.student.prn],
    ['Name', profile.student.full_name],
    ['Department', profile.student.department],
    ['Batch', String(profile.student.batch)],
    ['CGPA', profile.student.cgpa ?? '—'],
  ]

  return (
    <Card>
      <CardTitle hint="From the placement cell's roster. Contact them to correct it.">
        College record
      </CardTitle>

      <dl className="space-y-2 text-sm">
        {facts.map(([label, value]) => (
          <div key={label} className="flex justify-between gap-4">
            <dt className="text-ink-600">{label}</dt>
            <dd className="text-right font-medium">{value}</dd>
          </div>
        ))}
      </dl>

      <div className="mt-4 border-t border-ink-100 pt-4">
        {profile.is_verified ? (
          <Badge tone="success">Verified by the placement cell</Badge>
        ) : (
          <p className="text-sm text-ink-600">
            Not yet verified. The placement cell reviews profiles before companies see a verified
            badge.
          </p>
        )}
      </div>
    </Card>
  )
}
