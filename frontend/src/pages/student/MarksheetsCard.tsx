import { useState, type FormEvent } from 'react'

import { ApiError } from '@/api/client'
import {
  BOARDS,
  MARKSHEET_LEVELS,
  profilesApi,
  type Board,
  type MarksheetLevel,
  type OwnProfile,
} from '@/api/profiles'
import DocumentButton from '@/components/DocumentButton'
import { Alert, Button, Card, CardTitle, Field, Select } from '@/components/ui'

/**
 * School results: Class 10 and Class 12, each a marksheet file plus the marks.
 *
 * The file and the marks are two separate steps on purpose. Nothing is read
 * out of the file — unlike the college transcript, these are the student's own
 * statement, and the upload is the proof a verifier checks them against.
 */
export default function MarksheetsCard({
  profile,
  onProfile,
}: {
  profile: OwnProfile
  onProfile: (profile: OwnProfile) => void
}) {
  return (
    <Card>
      <CardTitle hint="Recruiters often ask for these. Only the placement cell can open the files.">
        School results
      </CardTitle>

      <div className="space-y-6">
        {MARKSHEET_LEVELS.map(({ level, label }) => (
          <LevelEntry key={level} level={level} label={label} profile={profile} onProfile={onProfile} />
        ))}
      </div>
    </Card>
  )
}

function LevelEntry({
  level,
  label,
  profile,
  onProfile,
}: {
  level: MarksheetLevel
  label: string
  profile: OwnProfile
  onProfile: (profile: OwnProfile) => void
}) {
  // Indexed rather than branched, so the two levels cannot drift apart.
  const url = profile[`marksheet_${level}_url`]
  const filename = profile[`marksheet_${level}_filename`]

  const [percentage, setPercentage] = useState(profile[`marks_${level}_percentage`] ?? '')
  const [board, setBoard] = useState<Board | ''>(profile[`marks_${level}_board`])
  const [year, setYear] = useState(
    profile[`marks_${level}_year`] === null ? '' : String(profile[`marks_${level}_year`]),
  )

  const [file, setFile] = useState<File | null>(null)
  const [busy, setBusy] = useState(false)
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)
  const [error, setError] = useState<ApiError | null>(null)

  function fail(caught: unknown, fallback: string) {
    setError(caught instanceof ApiError ? caught : new ApiError(0, fallback))
  }

  async function saveMarks(event: FormEvent) {
    event.preventDefault()
    setSaving(true)
    setError(null)
    setSaved(false)
    try {
      onProfile(
        await profilesApi.updateMe({
          [`marks_${level}_percentage`]: percentage.trim() || null,
          [`marks_${level}_board`]: board,
          [`marks_${level}_year`]: year.trim() ? Number(year) : null,
        }),
      )
      setSaved(true)
    } catch (caught) {
      fail(caught, 'Could not save the marks.')
    } finally {
      setSaving(false)
    }
  }

  async function upload() {
    if (!file) return
    setBusy(true)
    setError(null)
    try {
      onProfile(await profilesApi.uploadMarksheet(level, file))
      setFile(null)
    } catch (caught) {
      fail(caught, 'Could not upload the marksheet.')
    } finally {
      setBusy(false)
    }
  }

  async function remove() {
    setBusy(true)
    setError(null)
    try {
      onProfile(await profilesApi.deleteMarksheet(level))
    } catch (caught) {
      fail(caught, 'Could not remove the marksheet.')
    } finally {
      setBusy(false)
    }
  }

  const fieldError = (name: string) => error?.fieldErrors[name]

  return (
    <section aria-label={label} className="border-ink-100 not-first:border-t not-first:pt-6">
      <h3 className="mb-3 text-sm font-semibold text-ink-900">{label}</h3>

      {/* `file` errors have no control of their own to hang off, so they are
          shown here rather than silently dropped with the rest of the map. */}
      {error && (!Object.keys(error.fieldErrors).length || error.fieldErrors.file) ? (
        <div className="mb-3">
          <Alert tone="error">{(error.fieldErrors.file ?? [error.message]).join(' ')}</Alert>
        </div>
      ) : null}

      <form onSubmit={saveMarks} className="space-y-3" noValidate>
        <div className="grid gap-3 sm:grid-cols-3">
          <Field
            label="Percentage"
            name={`marks_${level}_percentage`}
            inputMode="decimal"
            placeholder="88.60"
            value={percentage}
            onChange={(event) => {
              setSaved(false)
              setPercentage(event.target.value)
            }}
            errors={fieldError(`marks_${level}_percentage`)}
          />
          <Select
            label="Board"
            name={`marks_${level}_board`}
            value={board}
            onChange={(event) => {
              setSaved(false)
              setBoard(event.target.value as Board | '')
            }}
          >
            <option value="">Not stated</option>
            {BOARDS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </Select>
          <Field
            label="Year of passing"
            name={`marks_${level}_year`}
            inputMode="numeric"
            placeholder="2022"
            value={year}
            onChange={(event) => {
              setSaved(false)
              setYear(event.target.value)
            }}
            errors={fieldError(`marks_${level}_year`)}
          />
        </div>
        <div className="flex items-center gap-3">
          <Button type="submit" size="sm" variant="secondary" loading={saving}>
            Save {label} marks
          </Button>
          {saved ? <span className="text-sm text-ok-600">Saved.</span> : null}
        </div>
      </form>

      {url ? (
        <div className="mt-3 flex flex-wrap items-center justify-between gap-3 rounded-lg border border-ink-200 bg-ink-50 p-3">
          <p className="min-w-0 truncate text-sm font-medium">{filename}</p>
          <span className="flex items-center gap-2">
            <DocumentButton url={url} filename={filename}>
              View
            </DocumentButton>
            <Button type="button" size="sm" variant="ghost" loading={busy} onClick={() => void remove()}>
              Remove
            </Button>
          </span>
        </div>
      ) : null}

      <div className="mt-3 flex flex-wrap items-end gap-3">
        <div className="min-w-0 flex-1">
          <label htmlFor={`marksheet-${level}`} className="block text-sm font-medium text-ink-800">
            {url ? `Replace ${label} marksheet` : `Upload ${label} marksheet`}
          </label>
          <input
            id={`marksheet-${level}`}
            type="file"
            accept="application/pdf,.pdf,image/png,image/jpeg,.png,.jpg,.jpeg"
            onChange={(event) => setFile(event.target.files?.[0] ?? null)}
            className="mt-1.5 block w-full text-sm"
          />
        </div>
        <Button type="button" size="sm" loading={busy} disabled={!file} onClick={() => void upload()}>
          Upload
        </Button>
      </div>
      <p className="mt-1.5 text-xs text-ink-400">PDF or a photo (PNG/JPG).</p>
    </section>
  )
}
