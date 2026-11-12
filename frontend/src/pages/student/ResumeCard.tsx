import { useEffect, useRef, useState } from 'react'

import DocumentButton from '@/components/DocumentButton'
import { ApiError } from '@/api/client'
import { describeMatchingError } from '@/api/matching'
import {
  isResumeAnalysis,
  profilesApi,
  type Agreement,
  type EducationLevel,
  type ExperienceKind,
  type OwnProfile,
  type ReadLevel,
  type ResumeAnalysis,
  type ResumeSuggestion,
  type SuggestedExperience,
} from '@/api/profiles'
import { Alert, Badge, Button, Card, CardTitle, Field, Select } from '@/components/ui'
import { KINDS } from '@/pages/student/experienceKinds'

const LEVEL_LABELS: Record<ReadLevel, string> = {
  UG: 'Undergraduate',
  Masters: 'Masters',
  PG: 'PG / Doctorate',
}

/**
 * Waits between polls of a pending reading. A reading is pending only
 * between the upload and the analyze call that answers with the finished
 * reading, so a page that opens on one is watching an earlier page's call
 * (the server finishes it even if that page closed). Bounded at about the
 * server's time budget (25 s): still pending after these, nothing is
 * reading it, and "Check again" asks for the reading itself.
 */
const POLL_DELAYS_MS = [1000, 2000, 4000, 8000, 8000]

type Phase = 'idle' | 'analysing' | 'polling' | 'stalled'

/**
 * Resume upload and the review step for what the parser read.
 *
 * The parsed values are a suggestion, never a verdict: they are shown next to
 * editable fields, and nothing is treated as confirmed until the student says
 * so — which is also what stops the next upload from overwriting a correction.
 *
 * After the quick read, the full reading (the AI model when it is on) runs,
 * and what it found that the form lacks is offered one item at a time.
 * Nothing is added to the profile without the student's click.
 */
export default function ResumeCard({
  profile,
  onProfile,
}: {
  profile: OwnProfile
  onProfile: (profile: OwnProfile) => void
}) {
  const fileInput = useRef<HTMLInputElement>(null)
  const [uploading, setUploading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [suggestion, setSuggestion] = useState<ResumeSuggestion | null>(null)

  const [years, setYears] = useState(profile.experience_years)
  const [level, setLevel] = useState<EducationLevel>(profile.education_level)
  const [savingReview, setSavingReview] = useState(false)
  const [reviewDone, setReviewDone] = useState(false)

  const [analysis, setAnalysis] = useState<ResumeAnalysis | null>(null)
  const [phase, setPhase] = useState<Phase>('idle')
  const [analysisError, setAnalysisError] = useState<string | null>(null)
  const [analysisNotice, setAnalysisNotice] = useState('')
  // Each run takes a number; a newer upload or a removal retires older runs.
  const runId = useRef(0)
  const alive = useRef(true)
  // Ends the current poll wait early, timer cleared, so nothing outlives the card.
  const cancelWait = useRef<(() => void) | null>(null)

  useEffect(() => {
    alive.current = true
    return () => {
      alive.current = false
      cancelWait.current?.()
    }
  }, [])

  function wait(ms: number) {
    return new Promise<void>((resolve) => {
      const timer = setTimeout(() => {
        cancelWait.current = null
        resolve()
      }, ms)
      cancelWait.current = () => {
        clearTimeout(timer)
        cancelWait.current = null
        resolve()
      }
    })
  }

  async function refreshProfile() {
    try {
      const fresh = await profilesApi.me()
      onProfile(fresh)
      if (!fresh.parsed_values_confirmed) {
        setYears(fresh.experience_years)
        setLevel(fresh.education_level)
      }
    } catch {
      // The reading is shown either way; the form catches up on next load.
    }
  }

  /**
   * Follow a reading to its end, from `first`: the analyze call, which
   * answers once the reading is finished, or a pending reading already in
   * hand, which is polled.
   */
  async function follow(first: () => Promise<unknown>) {
    cancelWait.current?.()
    const run = ++runId.current
    const current = () => alive.current && runId.current === run
    setPhase('analysing')
    setAnalysisError(null)
    setAnalysisNotice('')
    try {
      let reading = await first()
      let attempt = 0
      while (current() && isResumeAnalysis(reading) && reading.status === 'pending') {
        setAnalysis(reading)
        if (attempt >= POLL_DELAYS_MS.length) {
          setPhase('stalled')
          return
        }
        setPhase('polling')
        await wait(POLL_DELAYS_MS[attempt])
        attempt += 1
        if (!current()) return
        reading = await profilesApi.resumeAnalysis()
      }
      if (!current()) return
      if (isResumeAnalysis(reading)) {
        setAnalysis(reading)
        setAnalysisNotice('Resume analysis finished.')
        // Only the model's reading moves the pre-filled experience.
        if (reading.status === 'done' && reading.source === 'llm') await refreshProfile()
      }
      setPhase('idle')
    } catch (caught) {
      if (!current()) return
      setAnalysisError(
        describeMatchingError(
          caught,
          'The full reading did not finish. The values below come from the quick read.',
        ),
      )
      setPhase('idle')
    }
  }

  const readNow = () => follow(() => profilesApi.analyzeResume())

  const hasResume = profile.resume_filename !== ''

  useEffect(() => {
    if (!hasResume) return
    const run = runId.current
    profilesApi
      .resumeAnalysis()
      .then((reading) => {
        if (!alive.current || runId.current !== run || !isResumeAnalysis(reading)) return
        setAnalysis(reading)
        // An earlier page's reading, still under way: wait for it.
        if (reading.status === 'pending') void follow(async () => reading)
      })
      .catch(() => {
        // No reading yet is normal: the endpoint answers 404 until there is one.
      })
    // Only on mount: later readings arrive through upload and retry.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  async function handleUpload(file: File) {
    setUploading(true)
    setError(null)
    setReviewDone(false)
    let uploaded = false
    try {
      const result = await profilesApi.uploadResume(file)
      onProfile(result.profile)
      setSuggestion(result.suggestion)
      setYears(result.profile.experience_years)
      setLevel(result.profile.education_level)
      setAnalysis(isResumeAnalysis(result.analysis) ? result.analysis : null)
      uploaded = true
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : 'That file could not be read.')
    } finally {
      setUploading(false)
      if (fileInput.current) fileInput.current.value = ''
    }
    if (uploaded) await readNow()
  }

  async function handleConfirm() {
    setSavingReview(true)
    setError(null)
    try {
      onProfile(await profilesApi.confirmParsed(years, level))
      setReviewDone(true)
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : 'Could not save those values.')
    } finally {
      setSavingReview(false)
    }
  }

  async function handleRemove() {
    setError(null)
    try {
      await profilesApi.deleteResume()
      runId.current += 1
      cancelWait.current?.()
      setAnalysis(null)
      setPhase('idle')
      setAnalysisError(null)
      setAnalysisNotice('')
      onProfile(await profilesApi.me())
      setSuggestion(null)
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : 'Could not remove the resume.')
    }
  }

  const needsReview = profile.resume_filename !== '' && !profile.parsed_values_confirmed
  const busy = phase === 'analysing' || phase === 'polling'

  return (
    <Card>
      <CardTitle hint="PDF or DOCX. We read your years of experience and education level from it, for you to check.">
        Resume
      </CardTitle>

      <div className="space-y-4">
        {error ? <Alert tone="error">{error}</Alert> : null}

        {profile.resume_filename ? (
          <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-ink-200 bg-ink-50 p-3">
            <div className="min-w-0">
              <p className="truncate text-sm font-medium">{profile.resume_filename}</p>
              <p className="text-xs text-ink-400">
                Uploaded{' '}
                {profile.resume_uploaded_at
                  ? new Date(profile.resume_uploaded_at).toLocaleDateString()
                  : '—'}
              </p>
            </div>
            <div className="flex gap-2">
              {profile.resume_url ? (
                <DocumentButton url={profile.resume_url} filename={profile.resume_filename}>View</DocumentButton>
              ) : null}
              <Button size="sm" variant="ghost" onClick={handleRemove}>
                Remove
              </Button>
            </div>
          </div>
        ) : null}

        <div>
          <label htmlFor="resume-file" className="block text-sm font-medium text-ink-800">
            {profile.resume_filename ? 'Replace resume' : 'Upload resume'}
          </label>
          <input
            ref={fileInput}
            id="resume-file"
            type="file"
            accept=".pdf,.docx"
            disabled={uploading}
            onChange={(event) => {
              const file = event.target.files?.[0]
              if (file) void handleUpload(file)
            }}
            className="mt-1.5 block w-full text-sm text-ink-600 file:mr-3 file:rounded-md file:border-0 file:bg-ink-100 file:px-3 file:py-2 file:text-sm file:font-medium hover:file:bg-ink-200"
          />
          {uploading ? <p className="mt-2 text-sm text-ink-400">Reading your resume…</p> : null}
        </div>

        {suggestion ? (
          <Alert tone={suggestion.applied ? 'info' : 'warning'}>
            {suggestion.applied ? (
              <>
                We read <strong>{suggestion.experience_years} years</strong> of experience and{' '}
                <strong>
                  {suggestion.education_level
                    ? LEVEL_LABELS[suggestion.education_level]
                    : 'no education level'}
                </strong>{' '}
                from this resume, and filled them in below. Correct anything that is wrong.
              </>
            ) : (
              <>
                This resume reads as <strong>{suggestion.experience_years} years</strong>, which
                differs from the value you confirmed. Yours has been kept — update it below if the
                new resume is right.
              </>
            )}
          </Alert>
        ) : null}

        {hasResume ? (
          <div className="space-y-3">
            {/* Always rendered, at a fixed height, so polling never moves the page. */}
            <div className="flex min-h-8 flex-wrap items-center gap-3">
              <p role="status" aria-live="polite" className="text-sm text-ink-600">
                {phase === 'analysing'
                  ? 'Analysing…'
                  : phase === 'polling'
                    ? 'Analysing… still reading your resume.'
                    : phase === 'stalled'
                      ? 'This is taking longer than usual. Your quick-read values still count.'
                      : analysisNotice}
              </p>
              {phase === 'stalled' ? (
                <Button size="sm" variant="secondary" onClick={() => void readNow()}>
                  Check again
                </Button>
              ) : null}
            </div>

            {analysisError ? <Alert tone="error">{analysisError}</Alert> : null}

            {analysis && analysis.status !== 'pending' ? (
              <AnalysisPanel
                analysis={analysis}
                busy={busy}
                onRetry={() => void readNow()}
                onProfileChanged={async () => onProfile(await profilesApi.me())}
              />
            ) : null}
          </div>
        ) : null}

        {profile.resume_filename ? (
          <div className="rounded-lg border border-ink-200 p-4">
            <div className="mb-3 flex items-center justify-between gap-3">
              <p className="text-sm font-medium text-ink-800">From your resume</p>
              {needsReview ? (
                <Badge tone="warning">Needs your check</Badge>
              ) : reviewDone ? (
                <Badge tone="success">Confirmed</Badge>
              ) : (
                <Badge tone="success">Confirmed</Badge>
              )}
            </div>

            <div className="grid gap-3 sm:grid-cols-2">
              <Field
                label="Years of experience"
                name="experience_years"
                type="number"
                min={0}
                max={50}
                step="0.5"
                value={years}
                onChange={(event) => setYears(event.target.value)}
                hint={
                  profile.parsed_experience_years !== null
                    ? `Parser read ${profile.parsed_experience_years}`
                    : undefined
                }
              />
              <Select
                label="Education level"
                name="education_level"
                value={level}
                onChange={(event) => setLevel(event.target.value as EducationLevel)}
              >
                <option value="">Not stated</option>
                {Object.entries(LEVEL_LABELS).map(([value, label]) => (
                  <option key={value} value={value}>
                    {label}
                  </option>
                ))}
              </Select>
            </div>

            <Button
              className="mt-3"
              size="sm"
              loading={savingReview}
              onClick={handleConfirm}
              variant={needsReview ? 'primary' : 'secondary'}
            >
              {needsReview ? 'These are correct' : 'Save changes'}
            </Button>
          </div>
        ) : null}
      </div>
    </Card>
  )
}

/* ------------------------------------------------------- the reading --- */

interface ReadingRow {
  label: string
  ai: string | null
  pattern: string | null
  agree: boolean | null
}

function readingRow<T>(
  label: string,
  agreement: Agreement<T> | undefined,
  value: T | null,
  format: (value: T) => string,
): ReadingRow {
  const show = (reading: T | null | undefined) =>
    reading === null || reading === undefined ? null : format(reading)
  if (agreement) {
    return { label, ai: show(agreement.llm), pattern: show(agreement.regex), agree: agreement.agree }
  }
  // No comparison (the model was off): the reading is the pattern reader's.
  return { label, ai: null, pattern: show(value), agree: null }
}

const formatYears = (value: number) => `${value} year${value === 1 ? '' : 's'}`
const formatLevel = (value: ReadLevel) => LEVEL_LABELS[value] ?? value

function AnalysisPanel({
  analysis,
  busy,
  onRetry,
  onProfileChanged,
}: {
  analysis: ResumeAnalysis
  busy: boolean
  onRetry: () => void
  onProfileChanged: () => Promise<void>
}) {
  if (analysis.status === 'skipped') {
    return (
      <Alert tone="info">
        No text could be read from this resume, so there was nothing more to analyse. A text-based
        PDF or a DOCX reads best.
      </Alert>
    )
  }
  if (analysis.status === 'failed') {
    return (
      <Alert tone="warning" title="The full reading did not finish">
        <p>Your quick-read values below still count.</p>
        <Button size="sm" variant="secondary" className="mt-2" loading={busy} onClick={onRetry}>
          Try again
        </Button>
      </Alert>
    )
  }

  const byModel = analysis.source === 'llm'
  const rows = [
    readingRow('Experience', analysis.agreement.experience_years, analysis.experience_years, formatYears),
    readingRow('Education', analysis.agreement.education_level, analysis.education_level, formatLevel),
  ]
  const disagree = rows.some((row) => row.agree === false)

  return (
    <div className="space-y-4 rounded-lg border border-ink-200 p-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-sm font-medium text-ink-800">What the full reading found</p>
        <Badge tone={byModel ? 'brand' : 'neutral'}>
          {byModel
            ? `Read by the AI model${analysis.model_name ? ` (${analysis.model_name})` : ''}`
            : 'Read by pattern matching (regex)'}
        </Badge>
      </div>

      <table className="w-full text-sm">
        <caption className="sr-only">Values read from your resume</caption>
        <thead>
          <tr className="text-left text-xs text-ink-400">
            <th scope="col" className="pb-1 font-medium">
              Field
            </th>
            {byModel ? (
              <th scope="col" className="pb-1 font-medium">
                AI reading
              </th>
            ) : null}
            <th scope="col" className="pb-1 font-medium">
              Pattern reading
            </th>
            {byModel ? (
              <th scope="col" className="pb-1 font-medium">
                <span className="sr-only">Do they agree?</span>
              </th>
            ) : null}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.label} className="border-t border-ink-100">
              <th scope="row" className="py-1.5 text-left font-medium text-ink-800">
                {row.label}
              </th>
              {byModel ? <td className="py-1.5">{row.ai ?? '—'}</td> : null}
              <td className="py-1.5">{row.pattern ?? '—'}</td>
              {byModel ? (
                <td className="py-1.5 text-right">
                  {row.agree === null ? null : row.agree ? (
                    <Badge tone="success">Agree</Badge>
                  ) : (
                    <Badge tone="warning">Differ</Badge>
                  )}
                </td>
              ) : null}
            </tr>
          ))}
        </tbody>
      </table>

      {disagree ? (
        <p className="text-sm text-ink-600">
          The two readings differ. Check the values in the form below; yours are the ones that count.
        </p>
      ) : null}

      {analysis.retryable ? (
        <Alert tone="info" title="The AI reader did not finish">
          <p>These values come from pattern matching only. The AI model may read more.</p>
          <Button size="sm" variant="secondary" className="mt-2" loading={busy} onClick={onRetry}>
            Try the AI reading again
          </Button>
        </Alert>
      ) : null}

      <Suggestions
        key={analysis.analysed_at ?? 'unread'}
        skills={analysis.suggested_skills}
        experience={analysis.suggested_experience}
        onProfileChanged={onProfileChanged}
      />
    </div>
  )
}

/* -------------------------------------------------------- suggestions --- */

function monthYear(value: string | null): string {
  if (!value) return 'Present'
  return new Date(value).toLocaleDateString(undefined, {
    month: 'short',
    year: 'numeric',
    timeZone: 'UTC',
  })
}

function Suggestions({
  skills: initialSkills,
  experience: initialExperience,
  onProfileChanged,
}: {
  skills: string[]
  experience: SuggestedExperience[]
  onProfileChanged: () => Promise<void>
}) {
  const [skills, setSkills] = useState(initialSkills)
  const [experience, setExperience] = useState(initialExperience)
  const [busy, setBusy] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState('')

  if (!skills.length && !experience.length && !notice) return null

  async function addSkill(name: string) {
    setBusy(`skill:${name}`)
    setError(null)
    try {
      await profilesApi.addSkill(name, 'technical')
      setSkills((current) => current.filter((skill) => skill !== name))
      setNotice(`Added ${name} to your skills.`)
      await onProfileChanged()
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : `Could not add ${name}.`)
    } finally {
      setBusy(null)
    }
  }

  async function addExperience(item: SuggestedExperience, kind: ExperienceKind, key: string) {
    setBusy(key)
    setError(null)
    try {
      await profilesApi.addExperience({
        role: item.role,
        organization: item.organization,
        kind,
        start_date: item.start_date ?? undefined,
        end_date: item.end_date,
        description: item.description,
      })
      setExperience((current) => current.filter((entry) => entry !== item))
      setNotice(`Added ${item.role || item.organization} to your experience.`)
      await onProfileChanged()
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : 'Could not add that experience.')
    } finally {
      setBusy(null)
    }
  }

  return (
    <div className="space-y-4 border-t border-ink-100 pt-4">
      <div>
        <p className="text-sm font-medium text-ink-800">On your resume, not yet on your profile</p>
        <p className="text-xs text-ink-400">Nothing is added until you choose it.</p>
      </div>

      <p role="status" aria-live="polite" className="min-h-5 text-sm text-ok-600">
        {notice}
      </p>
      {error ? <Alert tone="error">{error}</Alert> : null}

      {skills.length ? (
        <div>
          <p className="text-xs font-medium tracking-wide text-ink-600 uppercase">Skills</p>
          <p className="text-xs text-ink-400">Added as technical skills.</p>
          <ul className="mt-2 flex flex-wrap gap-2" aria-label="Suggested skills">
            {skills.map((skill) => (
              <li key={skill}>
                <Button
                  size="sm"
                  variant="secondary"
                  loading={busy === `skill:${skill}`}
                  disabled={busy !== null}
                  aria-label={`Add ${skill}`}
                  onClick={() => void addSkill(skill)}
                >
                  <span aria-hidden>+</span>
                  {skill}
                </Button>
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      {experience.length ? (
        <div>
          <p className="text-xs font-medium tracking-wide text-ink-600 uppercase">Experience</p>
          <ul className="mt-2 space-y-3" aria-label="Suggested experience">
            {experience.map((item, index) => {
              const key = `experience:${index}:${item.role}:${item.organization}`
              return (
                <ExperienceSuggestion
                  key={key}
                  id={`suggested-experience-${index}`}
                  item={item}
                  busy={busy === key}
                  disabled={busy !== null}
                  onAdd={(kind) => void addExperience(item, kind, key)}
                />
              )
            })}
          </ul>
        </div>
      ) : null}
    </div>
  )
}

function ExperienceSuggestion({
  id,
  item,
  busy,
  disabled,
  onAdd,
}: {
  id: string
  item: SuggestedExperience
  busy: boolean
  disabled: boolean
  onAdd: (kind: ExperienceKind) => void
}) {
  // A kind the resume gave is shown pre-chosen; one it did not give is
  // asked for, never assumed.
  const [kind, setKind] = useState<ExperienceKind | ''>(item.kind ?? '')
  const [missingKind, setMissingKind] = useState(false)
  const title = [item.role, item.organization].filter(Boolean).join(' at ')

  return (
    <li className="rounded-lg border border-ink-200 p-3">
      <p id={`${id}-title`} className="text-sm font-medium text-ink-800">
        {title}
      </p>
      <p className="text-xs text-ink-400">
        {item.start_date ? `${monthYear(item.start_date)} – ${monthYear(item.end_date)}` : 'Dates not read'}
      </p>
      {item.description ? <p className="mt-1 text-sm text-ink-600">{item.description}</p> : null}

      <div className="mt-3 flex flex-wrap items-end gap-3">
        <div className="min-w-44">
          <Select
            label="Kind of role"
            id={`${id}-kind`}
            value={kind}
            aria-invalid={missingKind || undefined}
            aria-describedby={missingKind ? `${id}-kind-error` : undefined}
            onChange={(event) => {
              setKind(event.target.value as ExperienceKind | '')
              setMissingKind(false)
            }}
          >
            {item.kind ? null : <option value="">Choose a kind…</option>}
            {Object.entries(KINDS).map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </Select>
        </div>
        <Button
          size="sm"
          variant="secondary"
          loading={busy}
          disabled={disabled}
          aria-describedby={`${id}-title`}
          onClick={() => (kind ? onAdd(kind) : setMissingKind(true))}
        >
          Add to my experience
        </Button>
      </div>
      {missingKind ? (
        <p id={`${id}-kind-error`} role="alert" className="mt-2 text-sm text-bad-600">
          Choose what kind of role this was before adding it.
        </p>
      ) : null}
    </li>
  )
}
