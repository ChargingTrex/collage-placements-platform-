import { useEffect, useState, type FormEvent } from 'react'
import { Navigate, useNavigate } from 'react-router-dom'

import { ApiError } from '@/api/client'
import { profilesApi, type CareerPath, type Onboarding, type OwnProfile } from '@/api/profiles'
import { Alert, Button, Card, CardTitle, Field, PageHeader } from '@/components/ui'
import { CareerPathFields } from '@/pages/student/CareerPathCard'
import TranscriptCard from '@/pages/student/TranscriptCard'

/**
 * First-run form. Skippable on purpose: a hard gate guarantees data but also
 * abandoned registrations, so the portal stays usable and a banner on the
 * student home keeps asking until it is done.
 */
export default function OnboardingPage() {
  const navigate = useNavigate()
  const [data, setData] = useState<Onboarding | null>(null)
  // Only the transcript card needs the profile. If it fails to load the card
  // is left out: the transcript is optional and must not block the form.
  const [profile, setProfile] = useState<OwnProfile | null>(null)
  const [loadError, setLoadError] = useState<string | null>(null)

  const [phone, setPhone] = useState('')
  const [personalEmail, setPersonalEmail] = useState('')
  const [path, setPath] = useState<CareerPath | ''>('')
  const [detail, setDetail] = useState('')
  const [alsoPlacements, setAlsoPlacements] = useState(false)
  const [headline, setHeadline] = useState('')
  const [summary, setSummary] = useState('')

  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<ApiError | null>(null)

  useEffect(() => {
    let cancelled = false
    profilesApi
      .onboarding()
      .then((loaded) => {
        if (cancelled) return
        setData(loaded)
        setPhone(loaded.phone)
        setPersonalEmail(loaded.personal_email)
        // "Undecided" is the server default, so it means nothing chosen yet.
        setPath(loaded.career_path === 'undecided' ? '' : loaded.career_path)
        setDetail(loaded.career_path_detail)
        setAlsoPlacements(loaded.also_attending_placements)
        setHeadline(loaded.headline)
        setSummary(loaded.summary)
      })
      .catch((caught) => {
        if (!cancelled) {
          setLoadError(caught instanceof ApiError ? caught.message : 'Could not load the form.')
        }
      })
    profilesApi
      .me()
      .then((loaded) => {
        if (!cancelled) setProfile(loaded)
      })
      .catch(() => {})
    return () => {
      cancelled = true
    }
  }, [])

  if (loadError) return <Alert tone="error">{loadError}</Alert>
  if (!data) return <p className="py-16 text-center text-sm text-ink-400">Loading…</p>
  // Once completed the form never comes back.
  if (data.completed) return <Navigate to="/student" replace />

  function fail(field: string, message: string) {
    setError(new ApiError(400, message, { [field]: [message] }))
  }

  async function submit(event: FormEvent) {
    event.preventDefault()
    setError(null)
    if (!phone.trim()) return fail('phone', 'Enter your phone number.')
    if (!path) return fail('career_path', 'Choose what you plan to do after graduation.')
    if (path === 'other' && !detail.trim()) {
      return fail('career_path_detail', 'Tell us what "Other" means.')
    }

    setBusy(true)
    try {
      await profilesApi.submitOnboarding({
        phone: phone.trim(),
        personal_email: personalEmail.trim(),
        career_path: path,
        career_path_detail: path === 'other' ? detail.trim() : '',
        also_attending_placements: alsoPlacements,
        headline: headline.trim(),
        summary: summary.trim(),
      })
      navigate('/student', { replace: true })
    } catch (caught) {
      setError(caught instanceof ApiError ? caught : new ApiError(0, 'Could not save.'))
    } finally {
      setBusy(false)
    }
  }

  async function skip() {
    setBusy(true)
    try {
      await profilesApi.dismissOnboarding()
    } catch {
      // Skipping must never trap the student here; the banner asks again anyway.
    }
    navigate('/student', { replace: true })
  }

  const student = data.student
  const facts: Array<[string, string]> = [
    ['Name', student.full_name],
    ['PRN', student.prn],
    ['College email', student.email],
    ['Department', student.department],
    ['Batch', String(student.batch)],
  ]
  const fieldError = (field: string) => error?.fieldErrors[field]

  return (
    <>
      <PageHeader
        title="Welcome. A few details first."
        subtitle="This takes a minute. You can skip it and finish later from your dashboard."
      />

      <form onSubmit={submit} className="space-y-6" noValidate>
        <Card>
          <CardTitle hint="From the placement cell's roster. Tell them if anything is wrong.">
            Your college record
          </CardTitle>
          <dl className="space-y-1.5 text-sm">
            {facts.map(([label, value]) => (
              <div key={label} className="flex justify-between gap-4">
                <dt className="text-ink-600">{label}</dt>
                <dd className="font-medium">{value}</dd>
              </div>
            ))}
          </dl>
        </Card>

        <Card>
          <CardTitle>Contact</CardTitle>
          {error && !Object.keys(error.fieldErrors).length ? (
            <div className="mb-3">
              <Alert tone="error">{error.message}</Alert>
            </div>
          ) : null}
          <div className="grid gap-3 sm:grid-cols-2">
            <Field
              label="Phone"
              name="phone"
              type="tel"
              required
              value={phone}
              onChange={(event) => setPhone(event.target.value)}
              errors={fieldError('phone')}
            />
            <Field
              label="Personal email (optional)"
              name="personal_email"
              type="email"
              value={personalEmail}
              onChange={(event) => setPersonalEmail(event.target.value)}
              hint="Still reachable after your college address stops working."
              errors={fieldError('personal_email')}
            />
          </div>
        </Card>

        <Card>
          <CardTitle hint="Placement cell planning only. Companies do not see this.">
            After graduation
          </CardTitle>
          <div className="space-y-4">
            <CareerPathFields
              path={path}
              detail={detail}
              alsoPlacements={alsoPlacements}
              detailError={fieldError('career_path_detail')}
              onPath={setPath}
              onDetail={setDetail}
              onAlso={setAlsoPlacements}
            />
            {fieldError('career_path') ? (
              <p role="alert" className="text-sm text-bad-600">
                {fieldError('career_path')!.join(' ')}
              </p>
            ) : null}
          </div>
        </Card>

        <Card>
          <CardTitle hint="Optional. You can add these on your profile later.">About you</CardTitle>
          <div className="space-y-3">
            <Field
              label="Headline"
              name="headline"
              value={headline}
              onChange={(event) => setHeadline(event.target.value)}
              placeholder="Backend developer"
            />
            <div className="space-y-1.5">
              <label htmlFor="summary" className="block text-sm font-medium text-ink-800">
                Summary
              </label>
              <textarea
                id="summary"
                rows={3}
                value={summary}
                onChange={(event) => setSummary(event.target.value)}
                className="w-full rounded-lg border border-ink-200 px-3 py-2.5 text-sm focus:border-brand-500 focus:ring-2 focus:ring-brand-500/30 focus:outline-none"
              />
            </div>
          </div>
        </Card>

        <div className="flex items-center gap-3">
          <Button type="submit" loading={busy}>
            Save and continue
          </Button>
          <Button type="button" variant="ghost" disabled={busy} onClick={() => void skip()}>
            Skip for now
          </Button>
        </div>
      </form>

      {/* Outside the <form> (it has its own) and uploads on its own, so saving
          or skipping onboarding never depends on it. */}
      {profile ? (
        <div className="mt-6">
          <TranscriptCard profile={profile} onProfile={setProfile} />
        </div>
      ) : null}
    </>
  )
}
