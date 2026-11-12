import { useState } from 'react'

import { ApiError } from '@/api/client'
import { profilesApi, type ProjectEntry } from '@/api/profiles'
import { Alert, Button, Card, CardTitle, Field } from '@/components/ui'

type Draft = {
  title: string
  description: string
  tech_stack: string
  role: string
  team_size: string
  repo_url: string
  demo_url: string
  video_url: string
}

const EMPTY: Draft = {
  title: '',
  description: '',
  tech_stack: '',
  role: '',
  team_size: '',
  repo_url: '',
  demo_url: '',
  video_url: '',
}

function toDraft(project: ProjectEntry): Draft {
  return {
    title: project.title,
    description: project.description,
    tech_stack: project.tech_stack.join(', '),
    role: project.role,
    team_size: project.team_size === null ? '' : String(project.team_size),
    repo_url: project.repo_url,
    demo_url: project.demo_url,
    video_url: project.video_url,
  }
}

function toPayload(draft: Draft) {
  return {
    ...draft,
    team_size: draft.team_size ? Number(draft.team_size) : null,
    tech_stack: draft.tech_stack
      .split(',')
      .map((part) => part.trim())
      .filter(Boolean),
  }
}

const LINK_FIELDS = [
  ['repo_url', 'Repository'],
  ['demo_url', 'Live demo'],
  ['video_url', 'Video'],
] as const

export default function ProjectsCard({
  projects,
  onChanged,
}: {
  projects: ProjectEntry[]
  onChanged: () => Promise<void> | void
}) {
  const [editingId, setEditingId] = useState<string | 'new' | null>(null)
  const [draft, setDraft] = useState<Draft>(EMPTY)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<ApiError | null>(null)

  async function save() {
    setBusy(true)
    setError(null)
    try {
      if (editingId === 'new') await profilesApi.addProject(toPayload(draft))
      else if (editingId !== null) await profilesApi.updateProject(editingId, toPayload(draft))
      setEditingId(null)
      await onChanged()
    } catch (caught) {
      setError(caught instanceof ApiError ? caught : new ApiError(0, 'Could not save that project.'))
    } finally {
      setBusy(false)
    }
  }

  async function remove(project: ProjectEntry) {
    setBusy(true)
    setError(null)
    try {
      await profilesApi.deleteProject(project.id)
      await onChanged()
    } catch (caught) {
      setError(caught instanceof ApiError ? caught : new ApiError(0, 'Could not delete that project.'))
    } finally {
      setBusy(false)
    }
  }

  const set = (field: keyof Draft) => (event: { target: { value: string } }) =>
    setDraft((current) => ({ ...current, [field]: event.target.value }))

  const form = (
    <form
      className="space-y-3"
      onSubmit={(event) => {
        event.preventDefault()
        save()
      }}
    >
      <Field
        label="Title"
        name="title"
        value={draft.title}
        onChange={set('title')}
        required
        errors={error?.fieldErrors.title}
      />

      <div className="space-y-1.5">
        <label htmlFor="project-description" className="block text-sm font-medium text-ink-800">
          What it does
        </label>
        <textarea
          id="project-description"
          rows={3}
          value={draft.description}
          onChange={set('description')}
          className="w-full rounded-lg border border-ink-200 px-3 py-2.5 text-sm focus:border-brand-500 focus:ring-2 focus:ring-brand-500/30 focus:outline-none"
        />
      </div>

      <div className="grid gap-3 sm:grid-cols-2">
        <Field
          label="Tech stack"
          name="tech_stack"
          value={draft.tech_stack}
          onChange={set('tech_stack')}
          hint="Comma separated. Companies filter on these."
        />
        <Field label="Your role" name="role" value={draft.role} onChange={set('role')} />
        <Field
          label="Team size"
          name="team_size"
          type="number"
          min={1}
          value={draft.team_size}
          onChange={set('team_size')}
        />
      </div>

      <div className="grid gap-3 sm:grid-cols-3">
        {LINK_FIELDS.map(([field, label]) => (
          <Field
            key={field}
            label={label}
            name={field}
            type="url"
            placeholder="https://"
            value={draft[field]}
            onChange={set(field)}
            errors={error?.fieldErrors[field]}
          />
        ))}
      </div>

      <div className="flex gap-2">
        <Button type="submit" size="sm" loading={busy}>
          Save
        </Button>
        <Button type="button" size="sm" variant="ghost" onClick={() => setEditingId(null)}>
          Cancel
        </Button>
      </div>
    </form>
  )

  return (
    <Card>
      <div className="mb-4 flex items-start justify-between gap-4">
        <CardTitle hint="What you built, with links a recruiter can open.">Projects</CardTitle>
        {editingId === null ? (
          <Button
            size="sm"
            variant="secondary"
            onClick={() => {
              setDraft(EMPTY)
              setEditingId('new')
              setError(null)
            }}
          >
            Add project
          </Button>
        ) : null}
      </div>

      {error && !Object.keys(error.fieldErrors).length ? (
        <div className="mb-3">
          <Alert tone="error">{error.message}</Alert>
        </div>
      ) : null}

      {projects.length === 0 && editingId === null ? (
        <p className="text-sm text-ink-400">Nothing here yet.</p>
      ) : null}

      <ul className="space-y-3">
        {projects.map((project) => (
          <li key={project.id} className="rounded-lg border border-ink-200 p-4">
            {editingId === project.id ? (
              form
            ) : (
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div className="min-w-0">
                  <p className="font-medium">{project.title}</p>
                  {project.description ? (
                    <p className="mt-1 text-sm text-ink-600">{project.description}</p>
                  ) : null}
                  {project.tech_stack.length ? (
                    <p className="mt-2 text-xs text-ink-400">{project.tech_stack.join(' · ')}</p>
                  ) : null}
                  <p className="mt-2 flex flex-wrap gap-3 text-sm">
                    {LINK_FIELDS.filter(([field]) => project[field]).map(([field, label]) => (
                      <a
                        key={field}
                        href={project[field]}
                        target="_blank"
                        rel="noreferrer"
                        className="text-brand-600 hover:underline"
                      >
                        {label}
                      </a>
                    ))}
                  </p>
                </div>
                <div className="flex gap-1">
                  <Button
                    size="sm"
                    variant="ghost"
                    onClick={() => {
                      setDraft(toDraft(project))
                      setEditingId(project.id)
                      setError(null)
                    }}
                  >
                    Edit
                  </Button>
                  <Button size="sm" variant="ghost" onClick={() => remove(project)}>
                    Delete
                  </Button>
                </div>
              </div>
            )}
          </li>
        ))}

        {editingId === 'new' ? (
          <li className="rounded-lg border border-brand-500/40 bg-brand-50/40 p-4">{form}</li>
        ) : null}
      </ul>
    </Card>
  )
}
