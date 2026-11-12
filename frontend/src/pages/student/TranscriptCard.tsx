import { useState, type FormEvent } from 'react'

import { ApiError } from '@/api/client'
import { profilesApi, type OwnProfile } from '@/api/profiles'
import DocumentButton from '@/components/DocumentButton'
import { Alert, Button, Card, CardTitle } from '@/components/ui'

/**
 * CGPA comes from the college-issued transcript, never from the resume.
 * The roster CGPA is not changed by an upload; disagreements go to the
 * placement cell for review.
 */
export default function TranscriptCard({
  profile,
  onProfile,
}: {
  profile: OwnProfile
  onProfile: (profile: OwnProfile) => void
}) {
  const [file, setFile] = useState<File | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<ApiError | null>(null)

  async function upload(event: FormEvent) {
    event.preventDefault()
    if (!file) return
    setBusy(true)
    setError(null)
    try {
      onProfile(await profilesApi.uploadTranscript(file))
      setFile(null)
    } catch (caught) {
      setError(caught instanceof ApiError ? caught : new ApiError(0, 'Could not upload the transcript.'))
    } finally {
      setBusy(false)
    }
  }

  const hasTranscript = Boolean(profile.transcript_url)
  const mismatch = error?.reason === 'prn_mismatch'

  return (
    <Card>
      <CardTitle hint="Your CGPA is read from the transcript the college issued, not from your resume. PDF only.">
        Transcript
      </CardTitle>

      {mismatch ? (
        <div className="mb-4">
          <Alert tone="error" title="This transcript is not yours">
            <p>
              The PRN on it does not match your PRN, so it was not saved. Upload the transcript
              issued for your own PRN.
            </p>
          </Alert>
        </div>
      ) : error ? (
        <div className="mb-4">
          <Alert tone="error">{error.message}</Alert>
        </div>
      ) : null}

      {hasTranscript ? <TranscriptFacts profile={profile} /> : null}

      <form onSubmit={upload} className={hasTranscript ? 'mt-4 space-y-3' : 'space-y-3'}>
        <div>
          <label htmlFor="transcript-file" className="block text-sm font-medium text-ink-800">
            {hasTranscript ? 'Replace transcript' : 'Upload transcript'}
          </label>
          <input
            id="transcript-file"
            type="file"
            accept="application/pdf,.pdf"
            onChange={(event) => setFile(event.target.files?.[0] ?? null)}
            className="mt-1.5 block w-full text-sm"
          />
        </div>
        <Button type="submit" size="sm" loading={busy} disabled={!file}>
          Upload
        </Button>
      </form>

    </Card>
  )
}

function TranscriptFacts({ profile }: { profile: OwnProfile }) {
  const rows: Array<[string, string]> = [
    ['PRN on transcript', profile.transcript_prn || '—'],
    ['School', profile.transcript_school || '—'],
    ['Degree', profile.transcript_degree || '—'],
    ['CGPA printed', profile.parsed_cgpa ?? '—'],
    ['CGPA recomputed', profile.recomputed_cgpa ?? '—'],
    ['CGPA on the roster', profile.student.cgpa ?? '—'],
  ]

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-ink-200 bg-ink-50 p-3">
        <p className="min-w-0 truncate text-sm font-medium">{profile.transcript_filename}</p>
        {profile.transcript_url ? (
          <DocumentButton url={profile.transcript_url} filename={profile.transcript_filename}>View</DocumentButton>
        ) : null}
      </div>

      <dl className="space-y-1.5 text-sm">
        {rows.map(([label, value]) => (
          <div key={label} className="flex justify-between gap-4">
            <dt className="text-ink-600">{label}</dt>
            <dd className="font-medium tabular-nums">{value}</dd>
          </div>
        ))}
      </dl>

      {profile.cgpa_review_status === 'open' ? (
        <Alert tone="warning" title="The placement cell is reviewing your CGPA">
          The figures above do not agree with each other or with the roster, or the CGPA could not
          be read. Nothing for you to do unless you want to confirm the value below.
        </Alert>
      ) : null}
    </div>
  )
}
