import { useState } from 'react'

import { ApiError } from '@/api/client'
import { profilesApi, type ExperienceEntry } from '@/api/profiles'
import { Alert, Badge, Button, Card, CardTitle, Field, Select } from '@/components/ui'
import { KINDS } from '@/pages/student/experienceKinds'

type Draft = {
  role: string
  organization: string
  kind: ExperienceEntry['kind']
  start_date: string
  end_date: string
  location: string
  description: string
  skills_used: string
}

const EMPTY: Draft = {
  role: '',
  organization: '',
  kind: 'internship',
  start_date: '',
  end_date: '',
  location: '',
  description: '',
  skills_used: '',
}

function toDraft(entry: ExperienceEntry): Draft {
  return {
    role: entry.role,
    organization: entry.organization,
    kind: entry.kind,
    start_date: entry.start_date,
    end_date: entry.end_date ?? '',
    location: entry.location,
    description: entry.description,
    skills_used: entry.skills_used.join(', '),
  }
}

function toPayload(draft: Draft) {
  return {
    ...draft,
    // An empty end date means "still there", which the API models as null.
    end_date: draft.end_date || null,
    skills_used: draft.skills_used
      .split(',')
      .map((part) => part.trim())
      .filter(Boolean),
  }
}

function formatRange(entry: ExperienceEntry): string {
  const start = new Date(entry.start_date).toLocaleDateString(undefined, {
    month: 'short',
    year: 'numeric',
  })
  const end = entry.end_date
    ? new Date(entry.end_date).toLocaleDateString(undefined, { month: 'short', year: 'numeric' })
    : 'Present'
  return `${start} – ${end}`
}

export default function ExperienceCard({
  entries,
  onChanged,
}: {
  entries: ExperienceEntry[]
  onChanged: () => Promise<void> | void
}) {
  const [editingId, setEditingId] = useState<string | 'new' | null>(null)
  const [draft, setDraft] = useState<Draft>(EMPTY)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<ApiError | null>(null)

  function startNew() {
    setDraft(EMPTY)
    setEditingId('new')
    setError(null)
  }

  function startEdit(entry: ExperienceEntry) {
    setDraft(toDraft(entry))
    setEditingId(entry.id)
    setError(null)
  }

  async function save() {
    setBusy(true)
    setError(null)
    try {
      if (editingId === 'new') await profilesApi.addExperience(toPayload(draft))
      else if (editingId !== null) await profilesApi.updateExperience(editingId, toPayload(draft))
      setEditingId(null)
      await onChanged()
    } catch (caught) {
      setError(caught instanceof ApiError ? caught : new ApiError(0, 'Could not save that entry.'))
    } finally {
      setBusy(false)
    }
  }

  async function remove(entry: ExperienceEntry) {
    setBusy(true)
    setError(null)
    try {
      await profilesApi.deleteExperience(entry.id)
      await onChanged()
    } catch (caught) {
      setError(caught instanceof ApiError ? caught : new ApiError(0, 'Could not delete that entry.'))
    } finally {
      setBusy(false)
    }
  }

  const set = (field: keyof Draft) => (event: { target: { value: string } }) =>
    setDraft((current) => ({ ...current, [field]: event.target.value }))

  return (
    <Card>
      <div className="mb-4 flex items-start justify-between gap-4">
        <CardTitle hint="Internships, part-time work and volunteering.">Experience</CardTitle>
        {editingId === null ? (
          <Button size="sm" variant="secondary" onClick={startNew}>
            Add entry
          </Button>
        ) : null}
      </div>

      {error && !Object.keys(error.fieldErrors).length ? (
        <div className="mb-3">
          <Alert tone="error">{error.message}</Alert>
        </div>
      ) : null}

      {entries.length === 0 && editingId === null ? (
        <p className="text-sm text-ink-400">Nothing here yet.</p>
      ) : null}

      <ul className="space-y-3">
        {entries.map((entry) => (
          <li key={entry.id} className="rounded-lg border border-ink-200 p-4">
            {editingId === entry.id ? (
              <EntryForm
                draft={draft}
                set={set}
                error={error}
                busy={busy}
                onSave={save}
                onCancel={() => setEditingId(null)}
              />
            ) : (
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div className="min-w-0">
                  <p className="font-medium">
                    {entry.role}{' '}
                    <span className="font-normal text-ink-600">at {entry.organization}</span>
                  </p>
                  <p className="mt-0.5 flex flex-wrap items-center gap-2 text-sm text-ink-400">
                    <Badge>{KINDS[entry.kind]}</Badge>
                    {formatRange(entry)}
                    {entry.location ? <span>· {entry.location}</span> : null}
                    {entry.is_current ? <Badge tone="success">Current</Badge> : null}
                  </p>
                  {entry.description ? (
                    <p className="mt-2 text-sm text-ink-600">{entry.description}</p>
                  ) : null}
                  {entry.skills_used.length ? (
                    <p className="mt-2 text-xs text-ink-400">{entry.skills_used.join(' · ')}</p>
                  ) : null}
                </div>
                <div className="flex gap-1">
                  <Button size="sm" variant="ghost" onClick={() => startEdit(entry)}>
                    Edit
                  </Button>
                  <Button size="sm" variant="ghost" onClick={() => remove(entry)}>
                    Delete
                  </Button>
                </div>
              </div>
            )}
          </li>
        ))}

        {editingId === 'new' ? (
          <li className="rounded-lg border border-brand-500/40 bg-brand-50/40 p-4">
            <EntryForm
              draft={draft}
              set={set}
              error={error}
              busy={busy}
              onSave={save}
              onCancel={() => setEditingId(null)}
            />
          </li>
        ) : null}
      </ul>
    </Card>
  )
}

function EntryForm({
  draft,
  set,
  error,
  busy,
  onSave,
  onCancel,
}: {
  draft: Draft
  set: (field: keyof Draft) => (event: { target: { value: string } }) => void
  error: ApiError | null
  busy: boolean
  onSave: () => void
  onCancel: () => void
}) {
  return (
    <form
      className="space-y-3"
      onSubmit={(event) => {
        event.preventDefault()
        onSave()
      }}
    >
      <div className="grid gap-3 sm:grid-cols-2">
        <Field
          label="Role"
          name="role"
          value={draft.role}
          onChange={set('role')}
          required
          errors={error?.fieldErrors.role}
        />
        <Field
          label="Organisation"
          name="organization"
          value={draft.organization}
          onChange={set('organization')}
          required
          errors={error?.fieldErrors.organization}
        />
        <Select label="Type" name="kind" value={draft.kind} onChange={set('kind')}>
          {Object.entries(KINDS).map(([value, label]) => (
            <option key={value} value={value}>
              {label}
            </option>
          ))}
        </Select>
        <Field
          label="Location"
          name="location"
          value={draft.location}
          onChange={set('location')}
        />
        <Field
          label="Start date"
          name="start_date"
          type="date"
          value={draft.start_date}
          onChange={set('start_date')}
          required
          errors={error?.fieldErrors.start_date}
        />
        <Field
          label="End date"
          name="end_date"
          type="date"
          value={draft.end_date}
          onChange={set('end_date')}
          hint="Leave empty if you are still there."
          errors={error?.fieldErrors.end_date}
        />
      </div>

      <div className="space-y-1.5">
        <label htmlFor="description" className="block text-sm font-medium text-ink-800">
          What you did
        </label>
        <textarea
          id="description"
          rows={3}
          value={draft.description}
          onChange={set('description')}
          className="w-full rounded-lg border border-ink-200 px-3 py-2.5 text-sm focus:border-brand-500 focus:ring-2 focus:ring-brand-500/30 focus:outline-none"
        />
      </div>

      <Field
        label="Skills used"
        name="skills_used"
        value={draft.skills_used}
        onChange={set('skills_used')}
        hint="Comma separated."
      />

      <div className="flex gap-2">
        <Button type="submit" size="sm" loading={busy}>
          Save
        </Button>
        <Button type="button" size="sm" variant="ghost" onClick={onCancel}>
          Cancel
        </Button>
      </div>
    </form>
  )
}
