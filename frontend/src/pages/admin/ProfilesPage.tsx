import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'

import { ApiError } from '@/api/client'
import {
  careerPathLabel,
  profilesApi,
  type AdminProfile,
  type AdminProfileDetail,
  type JsonValue,
  type ProfileStats,
  type ResumeFactsAdmin,
  type VerificationFlag,
} from '@/api/profiles'
import { Alert, Badge, Button, Card, EmptyState, Field, PageHeader } from '@/components/ui'

const FILTERS = [
  { value: '', label: 'All' },
  { value: 'false', label: 'Awaiting verification' },
  { value: 'true', label: 'Verified' },
] as const

export default function ProfilesPage() {
  const [profiles, setProfiles] = useState<AdminProfile[]>([])
  const [stats, setStats] = useState<ProfileStats | null>(null)
  const [verified, setVerified] = useState<string>('')
  const [search, setSearch] = useState('')
  const [loading, setLoading] = useState(true)
  const [busyPrn, setBusyPrn] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async (verifiedFilter: string, term: string) => {
    setLoading(true)
    setError(null)
    try {
      const [page, aggregate] = await Promise.all([
        profilesApi.adminList({ verified: verifiedFilter, search: term }),
        profilesApi.adminStats(),
      ])
      setProfiles(page.results)
      setStats(aggregate)
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : 'Could not load profiles.')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void load(verified, search)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [verified])

  async function setVerification(profile: AdminProfile, isVerified: boolean) {
    setBusyPrn(profile.student.prn)
    setError(null)
    try {
      await profilesApi.setVerification(profile.student_id, isVerified)
      await load(verified, search)
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : 'Could not record that decision.')
    } finally {
      setBusyPrn(null)
    }
  }

  return (
    <>
      <PageHeader
        title="Student profiles"
        subtitle="Verify profiles so companies can trust the data behind them."
      />

      {stats ? (
        <div className="mb-6 grid gap-4 sm:grid-cols-4">
          {[
            ['Profiles', stats.profiles],
            ['Verified', stats.verified],
            ['With a resume', stats.with_resume],
            ['Avg. completion', `${stats.average_completion_percent}%`],
          ].map(([label, value]) => (
            <Card key={String(label)} className="p-4">
              <p className="text-2xl font-semibold tabular-nums">{value}</p>
              <p className="text-sm text-ink-600">{label}</p>
            </Card>
          ))}
        </div>
      ) : null}

      <div className="mb-4 flex flex-wrap items-end gap-3">
        <div className="flex gap-1 rounded-lg bg-ink-100 p-1">
          {FILTERS.map((filter) => (
            <button
              key={filter.label}
              type="button"
              onClick={() => setVerified(filter.value)}
              className={`rounded-md px-3 py-1.5 text-sm font-medium transition ${
                verified === filter.value
                  ? 'bg-white text-ink-900 shadow-sm'
                  : 'text-ink-600 hover:text-ink-800'
              }`}
            >
              {filter.label}
            </button>
          ))}
        </div>

        <form
          className="flex flex-1 items-end gap-2"
          onSubmit={(event) => {
            event.preventDefault()
            void load(verified, search)
          }}
        >
          <div className="min-w-48 flex-1">
            <Field
              label="Search"
              name="search"
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder="PRN, name or email"
            />
          </div>
          <Button type="submit" variant="secondary">
            Search
          </Button>
        </form>
      </div>

      {error ? (
        <div className="mb-4">
          <Alert tone="error">{error}</Alert>
        </div>
      ) : null}

      {loading ? (
        <p className="py-8 text-center text-sm text-ink-400">Loading…</p>
      ) : profiles.length === 0 ? (
        <EmptyState title="No profiles here">
          Students appear once they have signed up and opened their profile.
        </EmptyState>
      ) : (
        <div className="space-y-3">
          {profiles.map((profile) => (
            <Card key={profile.id} className="p-4">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div className="min-w-0">
                  <p className="flex flex-wrap items-center gap-2">
                    <Link
                      to={`/admin/profiles/${profile.student_id}`}
                      className="font-medium text-brand-700 hover:underline"
                    >
                      {profile.student.full_name}
                    </Link>
                    <span className="font-mono text-xs text-ink-400">{profile.student.prn}</span>
                    {profile.is_verified ? <Badge tone="success">Verified</Badge> : null}
                    <Badge tone={profile.visibility === 'hidden' ? 'warning' : 'neutral'}>
                      {profile.visibility}
                    </Badge>
                    <WarningBadge count={profile.warning_count ?? 0} />
                  </p>
                  <p className="text-sm text-ink-600">
                    {profile.student.department} · Batch {profile.student.batch} · CGPA{' '}
                    {profile.student.cgpa ?? '—'} · {careerPathLabel(profile.career_path)}
                  </p>
                  <p className="mt-1 text-sm text-ink-400">
                    {profile.completion_percent}% complete ·{' '}
                    {profile.experience_entries.length} experience ·{' '}
                    {profile.projects.length} projects ·{' '}
                    {profile.resume_filename ? 'resume uploaded' : 'no resume'}
                  </p>
                </div>

                <Button
                  size="sm"
                  variant={profile.is_verified ? 'secondary' : 'primary'}
                  loading={busyPrn === profile.student.prn}
                  onClick={() => setVerification(profile, !profile.is_verified)}
                >
                  {profile.is_verified ? 'Revoke verification' : 'Mark verified'}
                </Button>
              </div>

              <VerificationChecks
                studentId={profile.student_id}
                name={profile.student.full_name}
                flagCount={profile.verification_checks?.length ?? 0}
              />
            </Card>
          ))}
        </div>
      )}
    </>
  )
}

function WarningBadge({ count }: { count: number }) {
  return (
    <Badge tone={count ? 'warning' : 'neutral'}>
      {count} warning{count === 1 ? '' : 's'}
    </Badge>
  )
}

/**
 * The preliminary checks for one profile: where the resume, the form and
 * the roster disagree. Advice for the admin only; the verify button above
 * never depends on them.
 */
function VerificationChecks({
  studentId,
  name,
  flagCount,
}: {
  studentId: string
  name: string
  flagCount: number
}) {
  const [open, setOpen] = useState(false)
  const [detail, setDetail] = useState<AdminProfileDetail | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const panelId = `checks-${studentId}`

  async function toggle() {
    const next = !open
    setOpen(next)
    if (!next || detail) return
    setLoading(true)
    setError(null)
    try {
      setDetail(await profilesApi.adminProfile(studentId))
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : 'Could not load the checks.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="mt-3 border-t border-ink-100 pt-3">
      <Button
        size="sm"
        variant="ghost"
        aria-expanded={open}
        aria-controls={panelId}
        onClick={() => void toggle()}
      >
        {open ? 'Hide verification checks' : `Show verification checks (${flagCount})`}
        <span className="sr-only"> for {name}</span>
      </Button>

      <div id={panelId} hidden={!open} className="mt-3 space-y-4">
        <p role="status" aria-live="polite" className="text-sm text-ink-400">
          {loading ? 'Loading checks…' : ''}
        </p>
        {error ? <Alert tone="error">{error}</Alert> : null}
        {detail ? (
          <>
            <p className="text-xs text-ink-400">
              Preliminary checks, computed now from the resume, the form and the roster. They never
              block verification: you decide.
            </p>
            <FlagList flags={detail.verification_checks} analysed={detail.resume_facts_admin !== null} />
            {detail.resume_facts_admin ? (
              <ResumeFacts id={`${panelId}-resume-facts`} facts={detail.resume_facts_admin} />
            ) : null}
          </>
        ) : null}
      </div>
    </div>
  )
}

const SOURCE_LABELS: Record<string, string> = {
  roster: 'Roster',
  resume: 'Resume',
  form: 'Form',
  transcript: 'Transcript',
  regex: 'Pattern reading',
  llm: 'AI reading',
}

function sourceLabel(source: string): string {
  return SOURCE_LABELS[source] ?? source.replace(/_/g, ' ')
}

function formatValue(value: JsonValue): string {
  if (value === null || value === '') return '—'
  if (Array.isArray(value)) return value.length ? value.map(formatValue).join(', ') : '—'
  if (typeof value === 'object') return JSON.stringify(value)
  return String(value)
}

function FlagList({ flags, analysed }: { flags: VerificationFlag[]; analysed: boolean }) {
  if (!flags.length) {
    return (
      <p className="text-sm text-ink-600">
        {analysed
          ? 'No disagreements between the resume, the form and the roster.'
          : 'The resume has not been analysed yet, so there is nothing to compare.'}
      </p>
    )
  }
  return (
    <ul className="space-y-2" aria-label="Verification flags">
      {flags.map((flag, index) => (
        <li
          key={`${flag.field}-${index}`}
          className="rounded-lg border border-ink-200 p-3 text-sm"
        >
          <p className="flex flex-wrap items-center gap-2">
            <Badge tone={flag.severity === 'warning' ? 'warning' : 'neutral'}>
              {flag.severity === 'warning' ? 'Warning' : 'Info'}
            </Badge>
            <span className="text-ink-800">{flag.message}</span>
          </p>
          <p className="mt-1 text-xs text-ink-400">
            Sources: {flag.sources.map(sourceLabel).join(' vs ')}
          </p>
          {Object.keys(flag.values).length ? (
            <dl className="mt-2 grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 text-xs">
              {Object.entries(flag.values).map(([source, value]) => (
                <div key={source} className="contents">
                  <dt className="text-ink-600">{sourceLabel(source)}</dt>
                  <dd className="font-mono text-ink-800">{formatValue(value)}</dd>
                </div>
              ))}
            </dl>
          ) : null}
        </li>
      ))}
    </ul>
  )
}

function ResumeFacts({ id, facts }: { id: string; facts: ResumeFactsAdmin }) {
  const rows: Array<[string, string]> = [
    ['Age', facts.age === null ? '—' : String(facts.age)],
    ['Date of birth', facts.date_of_birth ?? '—'],
    ['CGPA on the resume', facts.cgpa === null ? '—' : String(facts.cgpa)],
    ['Phones', facts.phones.length ? facts.phones.join(', ') : '—'],
    ['Emails', facts.emails.length ? facts.emails.join(', ') : '—'],
  ]
  return (
    <section aria-labelledby={id} className="rounded-lg bg-ink-50 p-3">
      <h3 id={id} className="text-sm font-medium text-ink-800">
        From the resume — for verification only
      </h3>
      <p className="text-xs text-ink-400">
        Admins only: never shown to students or companies, and never used for eligibility. The
        roster stays authoritative.
      </p>
      <dl className="mt-2 grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 text-sm">
        {rows.map(([label, value]) => (
          <div key={label} className="contents">
            <dt className="text-ink-600">{label}</dt>
            <dd className="text-ink-800">{value}</dd>
          </div>
        ))}
      </dl>
    </section>
  )
}
