import { useState, type FormEvent } from 'react'

import { ApiError } from '@/api/client'
import {
  opportunitiesApi,
  type EducationLevelCode,
  type Opportunity,
  type OpportunityInput,
  type RoleType,
} from '@/api/opportunities'
import { Alert, Button, Field, Select } from '@/components/ui'

const LEVELS: EducationLevelCode[] = ['UG', 'Masters', 'PG']

function list(text: string): string[] {
  return text
    .split(',')
    .map((part) => part.trim())
    .filter(Boolean)
}

function numberOrNull(text: string): number | null {
  const trimmed = text.trim()
  if (!trimmed) return null
  const value = Number(trimmed)
  return Number.isFinite(value) ? value : null
}

/**
 * Create or edit a posting. Used by recruiters (their own company) and by
 * admins (who choose the company, and whose postings open directly: D28).
 */
export default function OpportunityForm({
  initial,
  isAdmin = false,
  onSaved,
  onCancel,
}: {
  initial?: Opportunity
  isAdmin?: boolean
  onSaved: (saved: Opportunity) => void
  onCancel: () => void
}) {
  const [company, setCompany] = useState(initial?.company ?? '')
  const [title, setTitle] = useState(initial?.title ?? '')
  const [description, setDescription] = useState(initial?.description ?? '')
  const [roleType, setRoleType] = useState<RoleType>(initial?.role_type ?? 'full_time')
  const [location, setLocation] = useState(initial?.location ?? '')
  const [openings, setOpenings] = useState(String(initial?.openings ?? 1))
  const [skills, setSkills] = useState((initial?.required_skills ?? []).join(', '))
  const [departments, setDepartments] = useState((initial?.eligible_departments ?? []).join(', '))
  const [minCgpa, setMinCgpa] = useState(initial?.min_cgpa != null ? String(initial.min_cgpa) : '')
  const [minExperience, setMinExperience] = useState(
    initial?.min_experience_years != null ? String(initial.min_experience_years) : '',
  )
  const [levels, setLevels] = useState<EducationLevelCode[]>(
    initial?.required_education_levels ?? [],
  )
  const [deadline, setDeadline] = useState(initial?.deadline ?? '')
  const [threshold, setThreshold] = useState(
    initial?.similarity_threshold != null ? String(initial.similarity_threshold) : '',
  )
  const [disclosed, setDisclosed] = useState(initial?.salary_disclosed ?? false)
  const [salaryMin, setSalaryMin] = useState(initial?.salary_min != null ? String(initial.salary_min) : '')
  const [salaryMax, setSalaryMax] = useState(initial?.salary_max != null ? String(initial.salary_max) : '')
  const [period, setPeriod] = useState<'month' | 'year'>(initial?.salary_period ?? 'year')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [fieldErrors, setFieldErrors] = useState<Record<string, string[]>>({})

  async function submit(event: FormEvent) {
    event.preventDefault()
    setError(null)
    setFieldErrors({})
    if (isAdmin && !initial && !company.trim()) {
      setFieldErrors({ company: ['Enter the company this posting is for.'] })
      return
    }
    const input: OpportunityInput = {
      title: title.trim(),
      description,
      role_type: roleType,
      location: location.trim(),
      openings: Number(openings) || 1,
      required_skills: list(skills),
      eligible_departments: list(departments),
      min_cgpa: numberOrNull(minCgpa),
      min_experience_years: numberOrNull(minExperience),
      required_education_levels: levels,
      salary_disclosed: disclosed,
      // Not disclosed means the salary fields travel as null.
      salary_min: disclosed ? numberOrNull(salaryMin) : null,
      salary_max: disclosed ? numberOrNull(salaryMax) : null,
      salary_period: period,
      deadline,
      similarity_threshold: numberOrNull(threshold),
    }
    if (isAdmin && !initial) input.company = company.trim()
    setSaving(true)
    try {
      const saved = initial
        ? await opportunitiesApi.update(initial.id, input)
        : await opportunitiesApi.create(input)
      onSaved(saved)
    } catch (caught) {
      if (caught instanceof ApiError) {
        setFieldErrors(caught.fieldErrors)
        setError(caught.message)
      } else setError('Could not save the posting.')
    } finally {
      setSaving(false)
    }
  }

  return (
    <form onSubmit={(event) => void submit(event)} className="space-y-4" aria-label="Opportunity form">
      {isAdmin && !initial ? (
        <Field
          label="Company ID"
          value={company}
          onChange={(event) => setCompany(event.target.value)}
          hint="The company's UUID. Postings you create open straight away."
          errors={fieldErrors.company}
        />
      ) : null}
      <div className="grid gap-4 sm:grid-cols-2">
        <Field label="Title" value={title} onChange={(e) => setTitle(e.target.value)} required errors={fieldErrors.title} />
        <Select label="Role type" value={roleType} onChange={(e) => setRoleType(e.target.value as RoleType)}>
          <option value="full_time">Full time</option>
          <option value="internship">Internship</option>
        </Select>
      </div>

      <div className="space-y-1.5">
        <label htmlFor="opp-description" className="block text-sm font-medium text-ink-800">
          Description
        </label>
        <textarea
          id="opp-description"
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          rows={6}
          required
          className="w-full rounded-lg border border-ink-200 bg-white px-3 py-2.5 text-sm focus:border-brand-500 focus:ring-2 focus:ring-brand-500/30 focus:outline-none"
        />
        <p className="text-xs text-ink-400">
          Applicants are scored against this text, so describe the work and the skills it needs.
        </p>
        {fieldErrors.description ? (
          <p className="text-sm text-bad-600">{fieldErrors.description.join(' ')}</p>
        ) : null}
      </div>

      <div className="grid gap-4 sm:grid-cols-3">
        <Field label="Location" value={location} onChange={(e) => setLocation(e.target.value)} />
        <Field label="Openings" type="number" min={1} value={openings} onChange={(e) => setOpenings(e.target.value)} errors={fieldErrors.openings} />
        <Field label="Deadline" type="date" value={deadline} onChange={(e) => setDeadline(e.target.value)} required errors={fieldErrors.deadline} />
      </div>

      <Field label="Required skills" value={skills} onChange={(e) => setSkills(e.target.value)} hint="Comma separated, for example: python, sql" errors={fieldErrors.required_skills} />
      <Field label="Eligible departments" value={departments} onChange={(e) => setDepartments(e.target.value)} hint="Comma separated programme names. Leave empty for all departments." errors={fieldErrors.eligible_departments} />

      <div className="grid gap-4 sm:grid-cols-3">
        <Field label="Minimum CGPA" type="number" step="0.01" min={0} max={10} value={minCgpa} onChange={(e) => setMinCgpa(e.target.value)} hint="Students below it cannot apply." errors={fieldErrors.min_cgpa} />
        <Field label="Minimum experience (years)" type="number" step="0.5" min={0} value={minExperience} onChange={(e) => setMinExperience(e.target.value)} hint="A screening filter, not an apply block." errors={fieldErrors.min_experience_years} />
        <Field label="Screening threshold (0 to 100)" type="number" min={0} max={100} value={threshold} onChange={(e) => setThreshold(e.target.value)} hint="Blank uses the default." errors={fieldErrors.similarity_threshold} />
      </div>

      <fieldset>
        <legend className="text-sm font-medium text-ink-800">Education levels accepted</legend>
        <p className="text-xs text-ink-400">A screening filter. Leave all unticked to accept any.</p>
        <div className="mt-1.5 flex gap-4">
          {LEVELS.map((level) => (
            <label key={level} className="flex items-center gap-1.5 text-sm">
              <input
                type="checkbox"
                checked={levels.includes(level)}
                onChange={(e) =>
                  setLevels((current) =>
                    e.target.checked ? [...current, level] : current.filter((l) => l !== level),
                  )
                }
              />
              {level}
            </label>
          ))}
        </div>
      </fieldset>

      <fieldset className="space-y-3">
        <legend className="text-sm font-medium text-ink-800">Salary</legend>
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" checked={!disclosed} onChange={(e) => setDisclosed(!e.target.checked)} />
          Not disclosed
        </label>
        {disclosed ? (
          <div className="grid gap-4 sm:grid-cols-3">
            <Field label="Salary from" type="number" min={0} value={salaryMin} onChange={(e) => setSalaryMin(e.target.value)} errors={fieldErrors.salary_min} />
            <Field label="Salary up to" type="number" min={0} value={salaryMax} onChange={(e) => setSalaryMax(e.target.value)} errors={fieldErrors.salary_max} />
            <Select label="Per" value={period} onChange={(e) => setPeriod(e.target.value as 'month' | 'year')}>
              <option value="year">Year</option>
              <option value="month">Month</option>
            </Select>
          </div>
        ) : null}
      </fieldset>

      {error ? <Alert tone="error">{error}</Alert> : null}

      <div className="flex gap-2">
        <Button type="submit" loading={saving}>
          {initial ? 'Save changes' : 'Create posting'}
        </Button>
        <Button type="button" variant="ghost" onClick={onCancel}>
          Cancel
        </Button>
      </div>
    </form>
  )
}
