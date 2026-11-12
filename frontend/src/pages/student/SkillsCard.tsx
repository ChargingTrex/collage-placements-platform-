import { useState, type FormEvent } from 'react'

import { ApiError } from '@/api/client'
import { profilesApi, type Skill } from '@/api/profiles'
import { Alert, Button, Card, CardTitle, Select } from '@/components/ui'

const CATEGORY_LABELS: Record<Skill['category'], string> = {
  technical: 'Technical',
  tool: 'Tool / platform',
  soft: 'Soft skill',
}

const CATEGORY_TONES: Record<Skill['category'], 'brand' | 'neutral' | 'success'> = {
  technical: 'brand',
  tool: 'neutral',
  soft: 'success',
}

export default function SkillsCard({
  skills,
  onChanged,
}: {
  skills: Skill[]
  onChanged: () => Promise<void> | void
}) {
  const [name, setName] = useState('')
  const [category, setCategory] = useState<Skill['category']>('technical')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function handleAdd(event: FormEvent) {
    event.preventDefault()
    if (!name.trim()) return
    setBusy(true)
    setError(null)
    try {
      await profilesApi.addSkill(name, category)
      setName('')
      await onChanged()
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : 'Could not add that skill.')
    } finally {
      setBusy(false)
    }
  }

  async function handleRemove(skill: Skill) {
    setError(null)
    try {
      await profilesApi.deleteSkill(skill.id)
      await onChanged()
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : 'Could not remove that skill.')
    }
  }

  const grouped = (['technical', 'tool', 'soft'] as const)
    .map((key) => ({ key, items: skills.filter((skill) => skill.category === key) }))
    .filter((group) => group.items.length > 0)

  return (
    <Card>
      <CardTitle hint="Companies filter on these, so spell them the way a recruiter would search.">
        Skills
      </CardTitle>

      {error ? (
        <div className="mb-3">
          <Alert tone="error">{error}</Alert>
        </div>
      ) : null}

      {grouped.length === 0 ? (
        <p className="mb-4 text-sm text-ink-400">No skills yet. Add at least three.</p>
      ) : (
        <div className="mb-4 space-y-3">
          {grouped.map((group) => (
            <div key={group.key}>
              <p className="mb-1.5 text-xs font-medium tracking-wide text-ink-400 uppercase">
                {CATEGORY_LABELS[group.key]}
              </p>
              <ul className="flex flex-wrap gap-2">
                {group.items.map((skill) => (
                  <li key={skill.id}>
                    <span
                      className={`inline-flex items-center gap-1.5 rounded-full py-1 pr-1 pl-3 text-sm ${
                        CATEGORY_TONES[group.key] === 'brand'
                          ? 'bg-brand-50 text-brand-700'
                          : CATEGORY_TONES[group.key] === 'success'
                            ? 'bg-ok-50 text-ok-600'
                            : 'bg-ink-100 text-ink-600'
                      }`}
                    >
                      {skill.name}
                      <button
                        type="button"
                        aria-label={`Remove ${skill.name}`}
                        onClick={() => handleRemove(skill)}
                        className="rounded-full px-1.5 text-xs hover:bg-black/10"
                      >
                        ×
                      </button>
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>
      )}

      <form onSubmit={handleAdd} className="flex flex-wrap items-end gap-2">
        <div className="min-w-40 flex-1">
          <label htmlFor="skill-name" className="block text-sm font-medium text-ink-800">
            Add a skill
          </label>
          <input
            id="skill-name"
            value={name}
            onChange={(event) => setName(event.target.value)}
            placeholder="e.g. PostgreSQL"
            className="mt-1.5 w-full rounded-lg border border-ink-200 px-3 py-2.5 text-sm focus:border-brand-500 focus:ring-2 focus:ring-brand-500/30 focus:outline-none"
          />
        </div>
        <div className="w-44">
          <Select
            label="Category"
            name="skill-category"
            value={category}
            onChange={(event) => setCategory(event.target.value as Skill['category'])}
          >
            {Object.entries(CATEGORY_LABELS).map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </Select>
        </div>
        <Button type="submit" loading={busy} disabled={!name.trim()}>
          Add
        </Button>
      </form>
    </Card>
  )
}
