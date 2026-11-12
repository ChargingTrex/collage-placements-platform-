import { useCallback, useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'

import { ApiError } from '@/api/client'
import {
  boardLabel,
  careerPathLabel,
  MARKSHEET_LEVELS,
  profilesApi,
  type AdminProfileDetail,
} from '@/api/profiles'
import DocumentButton from '@/components/DocumentButton'
import { Alert, Badge, Button, Card, CardTitle, PageHeader } from '@/components/ui'

/**
 * Everything the placement cell holds on one student. Hidden profiles are
 * fully visible here: visibility only limits companies.
 */
export default function ProfileDetailPage() {
  const { studentId = '' } = useParams()
  const [profile, setProfile] = useState<AdminProfileDetail | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)

  const load = useCallback(async () => {
    try {
      setProfile(await profilesApi.adminProfile(studentId))
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : 'Could not load this profile.')
    } finally {
      setLoading(false)
    }
  }, [studentId])

  useEffect(() => {
    void load()
  }, [load])

  async function act(action: () => Promise<AdminProfileDetail>, failure: string) {
    setBusy(true)
    setError(null)
    try {
      setProfile(await action())
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : failure)
    } finally {
      setBusy(false)
    }
  }

  if (loading) return <p className="py-16 text-center text-sm text-ink-400">Loading…</p>
  if (!profile) return <Alert tone="error">{error ?? 'Profile unavailable.'}</Alert>

  const roster = profile.student

  return (
    <>
      <p className="mb-3 text-sm">
        <Link to="/admin/profiles" className="text-brand-600 hover:underline">
          Back to profiles
        </Link>
      </p>

      <PageHeader
        title={roster.full_name}
        subtitle={`${roster.prn} · ${roster.department} · Batch ${roster.batch}`}
      />

      {error ? (
        <div className="mb-4">
          <Alert tone="error">{error}</Alert>
        </div>
      ) : null}

      <div className="grid gap-6 lg:grid-cols-3">
        <div className="space-y-6 lg:col-span-2">
          <Card>
            <CardTitle>Summary</CardTitle>
            <p className="font-medium">{profile.headline || 'No headline'}</p>
            <p className="mt-2 text-sm whitespace-pre-line text-ink-800">
              {profile.summary || 'No summary written.'}
            </p>

            <ul className="mt-4 flex flex-wrap gap-x-4 gap-y-1 text-sm" aria-label="Links">
              {[
                ['GitHub', profile.github_url],
                ['LinkedIn', profile.linkedin_url],
                ['Website', profile.website_url],
              ]
                .filter(([, url]) => url)
                .map(([label, url]) => (
                  <li key={label}>
                    <a
                      href={url}
                      target="_blank"
                      rel="noreferrer"
                      className="text-brand-600 hover:underline"
                    >
                      {label}
                    </a>
                  </li>
                ))}
            </ul>

            {profile.skills.length ? (
              <ul className="mt-4 flex flex-wrap gap-2" aria-label="Skills">
                {profile.skills.map((skill) => (
                  <li key={skill.id}>
                    <Badge tone="brand">{skill.name}</Badge>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="mt-4 text-sm text-ink-600">No skills listed.</p>
            )}
          </Card>

          <Card>
            <CardTitle>Experience</CardTitle>
            {profile.experience_entries.length ? (
              <ul className="space-y-3">
                {profile.experience_entries.map((entry) => (
                  <li key={entry.id} className="text-sm">
                    <p className="font-medium">
                      {entry.role} · {entry.organization}
                    </p>
                    <p className="text-xs text-ink-400">
                      {entry.start_date} to {entry.end_date ?? 'present'}
                    </p>
                    {entry.description ? (
                      <p className="mt-1 text-ink-600">{entry.description}</p>
                    ) : null}
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-sm text-ink-600">No experience entries.</p>
            )}
          </Card>

          <Card>
            <CardTitle>Projects</CardTitle>
            {profile.projects.length ? (
              <ul className="space-y-3">
                {profile.projects.map((project) => (
                  <li key={project.id} className="text-sm">
                    <p className="font-medium">{project.title}</p>
                    {project.tech_stack.length ? (
                      <p className="text-xs text-ink-400">{project.tech_stack.join(', ')}</p>
                    ) : null}
                    {project.description ? (
                      <p className="mt-1 text-ink-600">{project.description}</p>
                    ) : null}
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-sm text-ink-600">No projects.</p>
            )}
          </Card>
        </div>

        <div className="space-y-6">
          <Card>
            <CardTitle>Status</CardTitle>
            <p className="flex flex-wrap gap-2">
              <Badge tone={profile.is_verified ? 'success' : 'neutral'}>
                {profile.is_verified ? 'Verified' : 'Not verified'}
              </Badge>
              <Badge tone={profile.visibility === 'hidden' ? 'warning' : 'neutral'}>
                {profile.visibility}
              </Badge>
              <Badge tone={profile.onboarding_completed ? 'success' : 'warning'}>
                {profile.onboarding_completed ? 'Onboarding done' : 'Onboarding pending'}
              </Badge>
            </p>
            <Button
              className="mt-4"
              size="sm"
              variant={profile.is_verified ? 'secondary' : 'primary'}
              loading={busy}
              onClick={() =>
                void act(
                  () => profilesApi.setVerification(studentId, !profile.is_verified),
                  'Could not record that decision.',
                )
              }
            >
              {profile.is_verified ? 'Revoke verification' : 'Mark verified'}
            </Button>
          </Card>

          <Card>
            <CardTitle hint="For the placement cell's planning. Companies never see this.">
              Career path
            </CardTitle>
            <p className="text-sm font-medium">{careerPathLabel(profile.career_path)}</p>
            {profile.career_path === 'other' && profile.career_path_detail ? (
              <p className="text-sm text-ink-600">{profile.career_path_detail}</p>
            ) : null}
            {profile.also_attending_placements ? (
              <p className="mt-1 text-sm text-ink-600">Also attending placements.</p>
            ) : null}
          </Card>

          <Card>
            <CardTitle hint="Opens in a new tab. Each view is logged.">Documents</CardTitle>
            <div className="flex flex-wrap gap-3">
              {profile.resume_url ? (
                <DocumentButton url={profile.resume_url} filename={profile.resume_filename}>Open resume</DocumentButton>
              ) : (
                <p className="text-sm text-ink-600">No resume uploaded.</p>
              )}
              {profile.transcript_url ? (
                <DocumentButton
                  url={profile.transcript_url}
                  filename={profile.transcript_filename}
                >Open transcript</DocumentButton>
              ) : (
                <p className="text-sm text-ink-600">No transcript uploaded.</p>
              )}
              {MARKSHEET_LEVELS.map(({ level, label }) =>
                profile[`marksheet_${level}_url`] ? (
                  <DocumentButton
                    key={level}
                    url={profile[`marksheet_${level}_url`] as string}
                    filename={profile[`marksheet_${level}_filename`]}
                  >{`Open ${label} marksheet`}</DocumentButton>
                ) : null,
              )}
            </div>
          </Card>

          <Card>
            <CardTitle hint="The student's own statement; the marksheet above is the proof.">
              School results
            </CardTitle>
            <dl className="space-y-1.5 text-sm">
              {MARKSHEET_LEVELS.map(({ level, label }) => {
                const percentage = profile[`marks_${level}_percentage`]
                const board = profile[`marks_${level}_board`]
                const year = profile[`marks_${level}_year`]
                return (
                  <div key={level} className="flex justify-between gap-4">
                    <dt className="text-ink-600">{label}</dt>
                    <dd className="text-right font-medium">
                      {percentage === null ? (
                        <span className="text-ink-400">Not stated</span>
                      ) : (
                        <>
                          <span className="tabular-nums">{percentage}%</span>
                          <span className="ml-2 font-normal text-ink-600">
                            {board ? boardLabel(board) : '—'}
                            {year ? `, ${year}` : ''}
                          </span>
                        </>
                      )}
                    </dd>
                  </div>
                )
              })}
            </dl>
          </Card>

          <CgpaReviewPanel
            profile={profile}
            busy={busy}
            onResolve={() =>
              void act(() => profilesApi.adminCgpaReview(studentId), 'Could not resolve the review.')
            }
          />
        </div>
      </div>
    </>
  )
}

function CgpaReviewPanel({
  profile,
  busy,
  onResolve,
}: {
  profile: AdminProfileDetail
  busy: boolean
  onResolve: () => void
}) {
  // Driven by the server's list, so a source added there shows up here
  // without this panel having to learn about it.
  const sources = profile.cgpa_sources
  const rows = Object.entries(sources.labels).map(
    ([key, label]) => [key, label, sources.values[key]] as const,
  )
  const disagreeing = new Set(sources.disagreements.flatMap((item) => item.sources))
  const status = profile.cgpa_review_status

  return (
    <Card>
      <CardTitle hint="The roster CGPA is never overwritten by the transcript.">
        CGPA review
      </CardTitle>
      <dl className="space-y-1.5 text-sm">
        {rows.map(([key, label, value]) => (
          <div key={key} className="flex justify-between gap-4">
            <dt className="text-ink-600">
              {label}
              {disagreeing.has(key) ? (
                <span className="ml-1.5 align-middle">
                  <Badge tone="warning">differs</Badge>
                </span>
              ) : null}
            </dt>
            {/* Two decimals always: 8.4 and 8.40 are the same number but not
                the same grade, and these sit in a column to be compared. */}
            <dd className="font-medium tabular-nums">
              {value === null || value === undefined ? '—' : value.toFixed(2)}
            </dd>
          </div>
        ))}
      </dl>

      {sources.disagreements.length ? (
        <ul className="mt-3 space-y-1 text-sm text-ink-600">
          {sources.disagreements.map((item) => (
            <li key={item.sources.join('-')}>{item.message}</li>
          ))}
        </ul>
      ) : null}
      <p className="mt-3 flex items-center gap-2 text-sm">
        <Badge tone={status === 'open' ? 'warning' : status === 'resolved' ? 'success' : 'neutral'}>
          {status === 'open' ? 'Review open' : status === 'resolved' ? 'Resolved' : 'No review needed'}
        </Badge>
        {profile.cgpa_matches_roster === null ? null : (
          <span className="text-ink-600">
            {profile.cgpa_matches_roster ? 'Matches the roster' : 'Differs from the roster'}
          </span>
        )}
      </p>
      {status === 'open' ? (
        <Button className="mt-3" size="sm" loading={busy} onClick={onResolve}>
          Resolve
        </Button>
      ) : null}
    </Card>
  )
}
