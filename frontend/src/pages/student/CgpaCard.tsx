import { useState, type FormEvent } from 'react'

import { ApiError } from '@/api/client'
import { profilesApi, type OwnProfile } from '@/api/profiles'
import { Alert, Button, Card, CardTitle, Field } from '@/components/ui'

/**
 * The student's own CGPA, stated rather than parsed.
 *
 * Its own entry, separate from the transcript upload beside it, so a student
 * can state their CGPA before any transcript exists. What they type is a
 * claim: it is stored next to the roster's figure, the one printed on the
 * transcript and the one recomputed from the semesters, and it overwrites
 * none of them. The placement cell sees all four and decides.
 */
export default function CgpaCard({
  profile,
  onProfile,
}: {
  profile: OwnProfile
  onProfile: (profile: OwnProfile) => void
}) {
  const [value, setValue] = useState(profile.confirmed_cgpa ?? '')
  const [busy, setBusy] = useState(false)
  const [saved, setSaved] = useState(false)
  const [error, setError] = useState<ApiError | null>(null)

  async function save(event: FormEvent) {
    event.preventDefault()
    setBusy(true)
    setError(null)
    setSaved(false)
    try {
      onProfile(await profilesApi.confirmCgpa(value.trim()))
      setSaved(true)
    } catch (caught) {
      setError(caught instanceof ApiError ? caught : new ApiError(0, 'Could not save the CGPA.'))
    } finally {
      setBusy(false)
    }
  }

  const printed = profile.parsed_cgpa
  const differs =
    printed !== null &&
    profile.confirmed_cgpa !== null &&
    Math.abs(Number(printed) - Number(profile.confirmed_cgpa)) > 0.1

  return (
    <Card>
      <CardTitle hint="Your own figure. It is kept beside the roster's and the transcript's, never over them.">
        Your CGPA
      </CardTitle>

      <form onSubmit={save} className="space-y-3" noValidate>
        <Field
          label="CGPA"
          name="confirmed_cgpa"
          inputMode="decimal"
          placeholder="8.40"
          hint="Your cumulative GPA, between 0 and 10."
          value={value}
          onChange={(event) => {
            setSaved(false)
            setValue(event.target.value)
          }}
          errors={error ? (error.fieldErrors.cgpa ?? [error.message]) : undefined}
        />
        <div className="flex items-center gap-3">
          <Button type="submit" size="sm" loading={busy}>
            Save CGPA
          </Button>
          {saved ? <span className="text-sm text-ok-600">Saved.</span> : null}
        </div>
      </form>

      {differs ? (
        <div className="mt-4">
          <Alert tone="warning" title="This differs from your transcript">
            Your transcript shows {printed}. Both figures are kept, and the placement cell will
            check them. Correct yours here if you mistyped it.
          </Alert>
        </div>
      ) : null}

      {profile.cgpa_review_status === 'open' ? (
        <div className="mt-4">
          <Alert tone="info">
            The placement cell is reviewing your CGPA. Nothing for you to do.
          </Alert>
        </div>
      ) : null}
    </Card>
  )
}
