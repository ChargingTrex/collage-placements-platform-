import { useState, type FormEvent } from 'react'

import { ApiError } from '@/api/client'
import { CAREER_PATHS, profilesApi, type CareerPath, type OwnProfile } from '@/api/profiles'
import { Alert, Button, Card, CardTitle, Field } from '@/components/ui'

/**
 * What the student plans after graduation. Seen by the placement cell only,
 * never by companies: a recruiter learning a student is preparing for UPSC
 * would change how that student is treated. Any choice keeps full portal access.
 */
export default function CareerPathCard({
  profile,
  onProfile,
}: {
  profile: OwnProfile
  onProfile: (profile: OwnProfile) => void
}) {
  const [path, setPath] = useState<CareerPath>(profile.career_path)
  const [detail, setDetail] = useState(profile.career_path_detail)
  const [alsoPlacements, setAlsoPlacements] = useState(profile.also_attending_placements)
  const [busy, setBusy] = useState(false)
  const [saved, setSaved] = useState(false)
  const [error, setError] = useState<ApiError | null>(null)

  const needsDetail = path === 'other'
  const detailMissing = needsDetail && !detail.trim()

  async function save(event: FormEvent) {
    event.preventDefault()
    setSaved(false)
    if (detailMissing) {
      const message = 'Tell us what "Other" means.'
      setError(new ApiError(400, message, { career_path_detail: [message] }))
      return
    }
    setBusy(true)
    setError(null)
    try {
      onProfile(
        await profilesApi.updateMe({
          career_path: path,
          career_path_detail: needsDetail ? detail.trim() : '',
          also_attending_placements: alsoPlacements,
        }),
      )
      setSaved(true)
    } catch (caught) {
      setError(caught instanceof ApiError ? caught : new ApiError(0, 'Could not save.'))
    } finally {
      setBusy(false)
    }
  }

  return (
    <Card>
      <CardTitle hint="Helps the placement cell plan. Companies do not see this, and nothing in the portal depends on your answer.">
        After graduation
      </CardTitle>

      <form onSubmit={save} className="space-y-4" noValidate>
        {error && !Object.keys(error.fieldErrors).length ? (
          <Alert tone="error">{error.message}</Alert>
        ) : null}

        <CareerPathFields
          path={path}
          detail={detail}
          alsoPlacements={alsoPlacements}
          detailError={error?.fieldErrors.career_path_detail}
          onPath={(next) => {
            setSaved(false)
            setPath(next)
          }}
          onDetail={(next) => {
            setSaved(false)
            setDetail(next)
          }}
          onAlso={(next) => {
            setSaved(false)
            setAlsoPlacements(next)
          }}
        />

        <div className="flex items-center gap-3">
          <Button type="submit" loading={busy}>
            Save career path
          </Button>
          {saved ? <span className="text-sm text-ok-600">Saved.</span> : null}
        </div>
      </form>
    </Card>
  )
}

/** The radio list, shared with the onboarding form. */
export function CareerPathFields({
  path,
  detail,
  alsoPlacements,
  detailError,
  onPath,
  onDetail,
  onAlso,
}: {
  /** Empty when nothing is chosen yet (onboarding starts that way). */
  path: CareerPath | ''
  detail: string
  alsoPlacements: boolean
  detailError?: string[]
  onPath: (path: CareerPath) => void
  onDetail: (detail: string) => void
  onAlso: (value: boolean) => void
}) {
  return (
    <>
      <fieldset className="space-y-2">
        <legend className="sr-only">Career path</legend>
        {CAREER_PATHS.map((option) => (
          <label
            key={option.value}
            className={`flex cursor-pointer gap-3 rounded-lg border p-3 transition ${
              path === option.value ? 'border-brand-500 bg-brand-50' : 'border-ink-200 hover:bg-ink-50'
            }`}
          >
            <input
              type="radio"
              name="career_path"
              className="mt-1"
              value={option.value}
              checked={path === option.value}
              onChange={() => onPath(option.value)}
            />
            <span>
              <span className="block text-sm font-medium">{option.label}</span>
              <span className="block text-xs text-ink-600">{option.explain}</span>
            </span>
          </label>
        ))}
      </fieldset>

      {path === 'other' ? (
        <Field
          label="What are you planning?"
          name="career_path_detail"
          required
          value={detail}
          onChange={(event) => onDetail(event.target.value)}
          errors={detailError}
        />
      ) : null}

      <label className="flex items-center gap-2 text-sm">
        <input
          type="checkbox"
          checked={alsoPlacements}
          onChange={(event) => onAlso(event.target.checked)}
        />
        I am also attending placements
      </label>
    </>
  )
}
