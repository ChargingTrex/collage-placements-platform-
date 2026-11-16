import { useCallback, useEffect, useState, type FormEvent } from 'react'
import { Link, useParams } from 'react-router-dom'

import { areaOf } from '@/api/auth'
import { ApiError } from '@/api/client'
import { downloadFile } from '@/api/documents'
import { describeMatchingError } from '@/api/matching'
import {
  ALLOWED_TRANSITIONS,
  APPLICATION_STATUS_LABEL,
  opportunitiesApi,
  type ApplicationStatus,
  type CompanyApplication,
  type EducationLevelCode,
  type ScreenInput,
  type ScreenResult,
  type ScreenRow,
} from '@/api/opportunities'
import { useAuth } from '@/auth/AuthContext'
import DocumentButton from '@/components/DocumentButton'
import { ScoreBar } from '@/components/MatchDisplay'
import { ApplicationStatusBadge } from '@/components/StatusBadges'
import { Alert, Badge, Button, Card, CardTitle, EmptyState, Field, PageHeader } from '@/components/ui'

/** Only the moves the server allows; a finished application has none. */
function StatusControl({
  application,
  onMoved,
}: {
  application: CompanyApplication
  onMoved: (next: CompanyApplication) => void
}) {
  const options = ALLOWED_TRANSITIONS[application.status]
  const [target, setTarget] = useState<ApplicationStatus | ''>('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  if (!options.length) return <span className="text-xs text-ink-400">No further moves</span>

  async function move() {
    if (!target) return
    setBusy(true)
    setError(null)
    try {
      onMoved(await opportunitiesApi.setStatus(application.id, target))
      setTarget('')
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : 'Could not change the status.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="space-y-1">
      <div className="flex items-center gap-1.5">
        <select
          aria-label={`Move ${application.full_name} to`}
          value={target}
          onChange={(event) => setTarget(event.target.value as ApplicationStatus | '')}
          className="rounded-lg border border-ink-200 bg-white px-2 py-1.5 text-sm"
        >
          <option value="">Move to…</option>
          {options.map((status) => (
            <option key={status} value={status}>
              {APPLICATION_STATUS_LABEL[status]}
            </option>
          ))}
        </select>
        <Button size="sm" variant="secondary" disabled={!target} loading={busy} onClick={() => void move()}>
          Move
        </Button>
      </div>
      {error ? <p role="alert" className="text-xs text-bad-600">{error}</p> : null}
    </div>
  )
}

function ScreenTable({ title, rows, empty }: { title: string; rows: ScreenRow[]; empty: string }) {
  return (
    <section>
      <h3 className="text-sm font-semibold text-ink-900">
        {title} ({rows.length})
      </h3>
      {rows.length === 0 ? (
        <p className="mt-1 text-sm text-ink-400">{empty}</p>
      ) : (
        <table className="mt-2 w-full text-sm">
          <caption className="sr-only">{title}</caption>
          <thead>
            <tr className="text-left text-xs text-ink-400">
              <th scope="col" className="pb-1 font-medium">PRN</th>
              <th scope="col" className="pb-1 font-medium">Name</th>
              <th scope="col" className="pb-1 text-right font-medium">Score</th>
              <th scope="col" className="pb-1 text-right font-medium">Experience (years)</th>
              <th scope="col" className="pb-1 font-medium">Education</th>
              <th scope="col" className="pb-1 font-medium">Notes</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.application_id} className="border-t border-ink-100 align-top">
                <td className="py-1.5 tabular-nums">{row.prn}</td>
                <td className="py-1.5">{row.full_name}</td>
                <td className="py-1.5 text-right tabular-nums">{Math.round(row.score)}</td>
                <td className="py-1.5 text-right tabular-nums">{row.experience_years ?? '—'}</td>
                <td className="py-1.5">{row.education_levels.join(', ') || '—'}</td>
                <td className="py-1.5 text-ink-600">{row.reasons.join('; ')}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  )
}

function ScreenPanel({
  opportunityId,
  statusOf,
  onMoved,
}: {
  opportunityId: string
  /** Current status of an application, so only "applied" ones are moved. */
  statusOf: (applicationId: string) => ApplicationStatus | undefined
  onMoved: () => void
}) {
  const [moving, setMoving] = useState(false)
  const [moveNote, setMoveNote] = useState<string | null>(null)
  const [threshold, setThreshold] = useState('')
  const [minExperience, setMinExperience] = useState('')
  const [levels, setLevels] = useState<EducationLevelCode[]>([])
  const [running, setRunning] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [result, setResult] = useState<ScreenResult | null>(null)

  async function run(event: FormEvent) {
    event.preventDefault()
    // Blank fields are not sent, so the posting's own values apply.
    const input: ScreenInput = {}
    if (threshold.trim()) input.threshold = Number(threshold)
    if (minExperience.trim()) input.min_experience_years = Number(minExperience)
    if (levels.length) input.required_education_levels = levels
    setRunning(true)
    setError(null)
    try {
      setResult(await opportunitiesApi.screen(opportunityId, input))
    } catch (caught) {
      setResult(null)
      setError(describeMatchingError(caught, 'Could not screen the applicants.'))
    } finally {
      setRunning(false)
    }
  }

  /** Bulk step after screening: the legal move applied -> shortlisted, one by one. */
  async function shortlistAll() {
    if (!result) return
    const ids = result.shortlisted
      .map((row) => row.application_id)
      .filter((id) => statusOf(id) === 'applied')
    setMoving(true)
    setMoveNote(null)
    let moved = 0
    let failed = 0
    for (const id of ids) {
      try {
        await opportunitiesApi.setStatus(id, 'shortlisted', 'Passed screening')
        moved += 1
      } catch {
        failed += 1
      }
    }
    setMoving(false)
    setMoveNote(
      `Moved ${moved} applicant${moved === 1 ? '' : 's'} to Shortlisted.` +
        (failed ? ` ${failed} could not be moved.` : ''),
    )
    onMoved()
  }

  return (
    <Card className="mt-6">
      <CardTitle hint="Scores each applicant's resume as submitted against the posting. A guide for you to review, not a decision.">
        Screen applicants
      </CardTitle>
      <form onSubmit={(event) => void run(event)} className="space-y-4" aria-label="Screen applicants">
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Threshold (0 to 100)" type="number" min={0} max={100} value={threshold} onChange={(e) => setThreshold(e.target.value)} hint="Blank uses the posting's threshold." />
          <Field label="Minimum experience (years)" type="number" min={0} step="0.5" value={minExperience} onChange={(e) => setMinExperience(e.target.value)} />
        </div>
        <fieldset>
          <legend className="text-sm font-medium text-ink-800">Education required</legend>
          <div className="mt-1.5 flex gap-4">
            {(['UG', 'Masters', 'PG'] as const).map((level) => (
              <label key={level} className="flex items-center gap-1.5 text-sm">
                <input
                  type="checkbox"
                  checked={levels.includes(level)}
                  onChange={(e) =>
                    setLevels((current) =>
                      e.target.checked ? [...current, level] : current.filter((l) => l !== level),
                    )
                  }
                />
                {level}
              </label>
            ))}
          </div>
        </fieldset>
        <Button type="submit" loading={running}>
          Screen
        </Button>
      </form>

      {error ? <div className="mt-4"><Alert tone="error">{error}</Alert></div> : null}

      {result ? (
        <div className="mt-6 space-y-6">
          <ScreenTable title="Shortlisted" rows={result.shortlisted} empty="Nobody passed." />
          {result.shortlisted.some((row) => statusOf(row.application_id) === 'applied') ? (
            <Button variant="secondary" loading={moving} onClick={() => void shortlistAll()}>
              Move screened applicants to Shortlisted
            </Button>
          ) : null}
          {moveNote ? <Alert tone="success">{moveNote}</Alert> : null}
          <ScreenTable title="Below threshold" rows={result.below_threshold} empty="Nobody fell below the threshold." />
          <ScreenTable title="Filtered out" rows={result.filtered_out} empty="Nobody was filtered out." />
        </div>
      ) : null}
    </Card>
  )
}

export default function ApplicantsPage() {
  const { opportunityId = '' } = useParams()
  const { user } = useAuth()
  const backTo = user && areaOf(user) === 'admin' ? '/admin/opportunities' : '/company/opportunities'
  const [rows, setRows] = useState<CompanyApplication[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [exportError, setExportError] = useState<string | null>(null)
  const [exporting, setExporting] = useState(false)

  const load = useCallback(async () => {
    try {
      setRows(await opportunitiesApi.applications({ opportunity: opportunityId }))
      setError(null)
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : 'Could not load the applicants.')
    }
  }, [opportunityId])

  useEffect(() => {
    void load()
  }, [load])

  async function exportCsv() {
    setExporting(true)
    setExportError(null)
    try {
      await downloadFile(opportunitiesApi.applicantsExportUrl(opportunityId), 'applicants.csv')
    } catch (caught) {
      setExportError(caught instanceof Error ? caught.message : 'Could not export.')
    } finally {
      setExporting(false)
    }
  }

  const title = rows?.[0]?.opportunity.title

  return (
    <>
      <PageHeader
        title={title ? `Applicants: ${title}` : 'Applicants'}
        subtitle="The score is a guide to how well a resume reads against the posting, not a prediction."
      />
      <div className="mb-4 flex items-center justify-between">
        <Link to={backTo} className="text-sm text-brand-700 underline">
          Back to postings
        </Link>
        <Button variant="secondary" loading={exporting} onClick={() => void exportCsv()}>
          Export CSV
        </Button>
      </div>
      {exportError ? <div className="mb-4"><Alert tone="error">{exportError}</Alert></div> : null}
      {error ? <Alert tone="error">{error}</Alert> : null}

      {rows === null && !error ? (
        <p className="py-8 text-center text-sm text-ink-400">Loading…</p>
      ) : rows && rows.length === 0 ? (
        <EmptyState title="No applicants yet" />
      ) : rows ? (
        <div className="overflow-x-auto rounded-xl border border-ink-200 bg-white">
          <table className="w-full text-sm">
            <caption className="sr-only">Applicants</caption>
            <thead>
              <tr className="text-left text-xs text-ink-400">
                <th scope="col" className="p-3 font-medium">Student</th>
                <th scope="col" className="p-3 font-medium">Match</th>
                <th scope="col" className="p-3 font-medium">Eligibility</th>
                <th scope="col" className="p-3 font-medium">Status</th>
                <th scope="col" className="p-3 font-medium">Resume</th>
                <th scope="col" className="p-3 font-medium">Move</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.id} className="border-t border-ink-100 align-top">
                  <td className="p-3">
                    <p className="font-medium">{row.full_name}</p>
                    <p className="text-xs text-ink-400 tabular-nums">{row.prn}</p>
                    <p className="text-xs text-ink-600">
                      {row.department} · CGPA {row.cgpa_at_apply ?? '—'}
                    </p>
                    {row.skills.length ? (
                      <p className="text-xs text-ink-600">{row.skills.join(', ')}</p>
                    ) : null}
                    {/* Contact details exist only for verified profiles. */}
                    {row.contact_available && row.contact ? (
                      <p className="text-xs text-ink-600">
                        {row.contact.email} · {row.contact.phone}
                      </p>
                    ) : null}
                  </td>
                  <td className="w-44 p-3">
                    <ScoreBar score={row.score} size="sm" />
                  </td>
                  <td className="p-3">
                    <Badge tone={row.eligible ? 'success' : 'warning'}>
                      {row.eligible ? 'Eligible' : 'Not eligible'}
                    </Badge>
                    {row.eligibility_reasons.map((reason) => (
                      <p key={reason} className="text-xs text-ink-600">{reason}</p>
                    ))}
                  </td>
                  <td className="p-3">
                    <ApplicationStatusBadge status={row.status} />
                  </td>
                  <td className="p-3">
                    {/* The snapshot taken at apply time, opened through the audited route. */}
                    {row.resume_url ? (
                      <DocumentButton url={row.resume_url} filename={`${row.prn}-resume`}>
                        Open resume
                      </DocumentButton>
                    ) : (
                      <span className="text-xs text-ink-400">None</span>
                    )}
                  </td>
                  <td className="p-3">
                    <StatusControl
                      application={row}
                      onMoved={(next) =>
                        setRows((current) =>
                          current ? current.map((r) => (r.id === next.id ? { ...r, status: next.status } : r)) : current,
                        )
                      }
                    />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}

      <ScreenPanel
        opportunityId={opportunityId}
        statusOf={(id) => rows?.find((row) => row.id === id)?.status}
        onMoved={() => void load()}
      />
    </>
  )
}
