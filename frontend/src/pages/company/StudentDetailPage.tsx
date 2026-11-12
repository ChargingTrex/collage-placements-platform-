import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'

import { ApiError } from '@/api/client'
import { profilesApi, type CompanyProfile } from '@/api/profiles'
import DocumentButton from '@/components/DocumentButton'
import { Alert, Badge, Button, Card, CardTitle, PageHeader } from '@/components/ui'

export default function StudentDetailPage() {
  const { studentId = '' } = useParams()
  const [profile, setProfile] = useState<CompanyProfile | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)

  async function load() {
    setLoading(true)
    try {
      setProfile(await profilesApi.student(studentId))
      setError(null)
    } catch (caught) {
      setError(
        caught instanceof ApiError && caught.status === 404
          ? 'This profile is not visible to you.'
          : 'Could not load this profile.',
      )
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void load()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [studentId])

  if (loading) return <p className="py-16 text-center text-sm text-ink-400">Loading…</p>

  if (!profile) {
    return (
      <>
        <Alert tone="error">{error ?? 'Not found.'}</Alert>
        <Link to="/company/students" className="mt-4 inline-block text-sm text-brand-600 hover:underline">
          Back to search
        </Link>
      </>
    )
  }

  async function toggleShortlist() {
    if (!profile) return
    if (profile.is_shortlisted) await profilesApi.unshortlist(profile.student_id)
    else await profilesApi.shortlist(profile.student_id)
    await load()
  }

  return (
    <>
      <Link to="/company/students" className="mb-4 inline-block text-sm text-brand-600 hover:underline">
        ← Back to search
      </Link>

      <div className="mb-6 flex flex-wrap items-start justify-between gap-4">
        <div>
          <PageHeader
            title={profile.student.full_name}
            subtitle={`${profile.headline || '—'} · ${profile.student.department} · Batch ${profile.student.batch}`}
          />
          <div className="-mt-4 flex flex-wrap gap-2">
            {profile.is_verified ? <Badge tone="success">Verified by the placement cell</Badge> : null}
            <Badge>CGPA {profile.student.cgpa ?? '—'}</Badge>
            <Badge>{profile.experience_years} yrs experience</Badge>
            {profile.education_level ? <Badge>{profile.education_level}</Badge> : null}
          </div>
        </div>

        <Button variant={profile.is_shortlisted ? 'secondary' : 'primary'} onClick={toggleShortlist}>
          {profile.is_shortlisted ? 'Remove from shortlist' : 'Shortlist'}
        </Button>
      </div>

      <div className="grid gap-6 lg:grid-cols-3">
        <div className="space-y-6 lg:col-span-2">
          {profile.summary ? (
            <Card>
              <CardTitle>Summary</CardTitle>
              <p className="text-sm whitespace-pre-line text-ink-600">{profile.summary}</p>
            </Card>
          ) : null}

          <Card>
            <CardTitle>Experience</CardTitle>
            {profile.experience_entries.length === 0 ? (
              <p className="text-sm text-ink-400">None listed.</p>
            ) : (
              <ul className="space-y-4">
                {profile.experience_entries.map((entry) => (
                  <li key={entry.id}>
                    <p className="font-medium">
                      {entry.role} <span className="font-normal text-ink-600">at {entry.organization}</span>
                    </p>
                    <p className="text-sm text-ink-400">
                      {entry.duration_months} months{entry.is_current ? ' · current' : ''}
                    </p>
                    {entry.description ? (
                      <p className="mt-1 text-sm text-ink-600">{entry.description}</p>
                    ) : null}
                  </li>
                ))}
              </ul>
            )}
          </Card>

          <Card>
            <CardTitle>Projects</CardTitle>
            {profile.projects.length === 0 ? (
              <p className="text-sm text-ink-400">None listed.</p>
            ) : (
              <ul className="space-y-4">
                {profile.projects.map((project) => (
                  <li key={project.id}>
                    <p className="font-medium">{project.title}</p>
                    {project.description ? (
                      <p className="mt-1 text-sm text-ink-600">{project.description}</p>
                    ) : null}
                    {project.tech_stack.length ? (
                      <p className="mt-1 text-xs text-ink-400">{project.tech_stack.join(' · ')}</p>
                    ) : null}
                    <p className="mt-1 flex gap-3 text-sm">
                      {project.repo_url ? (
                        <a href={project.repo_url} target="_blank" rel="noreferrer" className="text-brand-600 hover:underline">
                          Repository
                        </a>
                      ) : null}
                      {project.demo_url ? (
                        <a href={project.demo_url} target="_blank" rel="noreferrer" className="text-brand-600 hover:underline">
                          Live demo
                        </a>
                      ) : null}
                    </p>
                  </li>
                ))}
              </ul>
            )}
          </Card>
        </div>

        <div className="space-y-6">
          <Card>
            <CardTitle>Skills</CardTitle>
            {profile.skills.length === 0 ? (
              <p className="text-sm text-ink-400">None listed.</p>
            ) : (
              <ul className="flex flex-wrap gap-1.5">
                {profile.skills.map((skill) => (
                  <li key={skill.id} className="rounded-full bg-ink-100 px-2.5 py-1 text-xs text-ink-600">
                    {skill.name}
                  </li>
                ))}
              </ul>
            )}
          </Card>

          <Card>
            <CardTitle hint="Shown once the placement cell has verified the profile.">
              Contact
            </CardTitle>
            {profile.contact ? (
              <dl className="space-y-2 text-sm">
                <div className="flex justify-between gap-4">
                  <dt className="text-ink-600">Email</dt>
                  <dd className="text-right">{profile.contact.email}</dd>
                </div>
                <div className="flex justify-between gap-4">
                  <dt className="text-ink-600">Phone</dt>
                  <dd className="text-right">{profile.contact.phone || '—'}</dd>
                </div>
              </dl>
            ) : (
              <p className="text-sm text-ink-600">
                Contact details appear once this profile is verified.
              </p>
            )}
            {profile.resume_url ? (
              <div className="mt-4">
                <DocumentButton url={profile.resume_url}>Open resume</DocumentButton>
              </div>
            ) : null}
          </Card>
        </div>
      </div>
    </>
  )
}
