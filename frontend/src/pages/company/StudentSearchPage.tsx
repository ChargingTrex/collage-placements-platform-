import { useCallback, useEffect, useState, type FormEvent } from 'react'
import { Link } from 'react-router-dom'

import { ApiError } from '@/api/client'
import {
  describeMatchingError,
  JD_MIN_CHARS,
  matchingApi,
  type MatchResult,
  type MatchSearchResponse,
  type RoleCategory,
} from '@/api/matching'
import { profilesApi, type CompanyProfile, type StudentSearchParams } from '@/api/profiles'
import { MatchBreakdown, ScoreBar, SkillChips } from '@/components/MatchDisplay'
import {
  Alert,
  Badge,
  Button,
  Card,
  CardTitle,
  EmptyState,
  Field,
  PageHeader,
  Select,
} from '@/components/ui'

const EMPTY_FILTERS: StudentSearchParams = {
  search: '',
  department: '',
  skills: '',
  project_keyword: '',
  cgpa_min: '',
  cgpa_max: '',
  verified: '',
  category: '',
}

export default function StudentSearchPage() {
  // `filters` is the form as typed; `applied` is what the list shows, and
  // what the JD match narrows by, so the two lists never disagree.
  const [filters, setFilters] = useState<StudentSearchParams>(EMPTY_FILTERS)
  const [applied, setApplied] = useState<StudentSearchParams>(EMPTY_FILTERS)
  const [results, setResults] = useState<CompanyProfile[]>([])
  const [count, setCount] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [categories, setCategories] = useState<RoleCategory[]>([])
  const [ranked, setRanked] = useState<MatchSearchResponse | null>(null)

  useEffect(() => {
    let cancelled = false
    matchingApi
      .categories()
      .then((all) => !cancelled && setCategories(all))
      .catch(() => {
        // Without categories the filter offers "Any" only; browsing still works.
      })
    return () => {
      cancelled = true
    }
  }, [])

  const load = useCallback(async (params: StudentSearchParams) => {
    setLoading(true)
    setError(null)
    setApplied(params)
    try {
      const page = await profilesApi.searchStudents(params)
      setResults(page.results)
      setCount(page.count)
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : 'Could not load profiles.')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void load(EMPTY_FILTERS)
  }, [load])

  function submit(event: FormEvent) {
    event.preventDefault()
    void load(filters)
  }

  const set = (field: keyof StudentSearchParams) => (event: { target: { value: string } }) =>
    setFilters((current) => ({ ...current, [field]: event.target.value }))

  async function toggleShortlist(profile: CompanyProfile) {
    try {
      if (profile.is_shortlisted) await profilesApi.unshortlist(profile.student_id)
      else await profilesApi.shortlist(profile.student_id)
      await load(applied)
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : 'Could not update the shortlist.')
    }
  }

  return (
    <>
      <PageHeader
        title="Browse students"
        subtitle="Standardised profiles you can filter. Students choose who sees theirs."
      />

      <div className="grid gap-6 lg:grid-cols-4">
        <Card className="lg:col-span-1">
          <form onSubmit={submit} className="space-y-3">
            <Field
              label="Search"
              name="search"
              value={filters.search ?? ''}
              onChange={set('search')}
              placeholder="Name, PRN or headline"
            />
            <Field
              label="Department"
              name="department"
              value={filters.department ?? ''}
              onChange={set('department')}
              placeholder="Computer Engineering"
            />
            <Field
              label="Skills"
              name="skills"
              value={filters.skills ?? ''}
              onChange={set('skills')}
              placeholder="python, django"
              hint="Comma separated. All must be present."
            />
            <Field
              label="Project keyword"
              name="project_keyword"
              value={filters.project_keyword ?? ''}
              onChange={set('project_keyword')}
              placeholder="e.g. dashboard"
            />
            <div className="grid grid-cols-2 gap-2">
              <Field
                label="CGPA from"
                name="cgpa_min"
                type="number"
                step="0.01"
                min={0}
                max={10}
                value={filters.cgpa_min ?? ''}
                onChange={set('cgpa_min')}
              />
              <Field
                label="to"
                name="cgpa_max"
                type="number"
                step="0.01"
                min={0}
                max={10}
                value={filters.cgpa_max ?? ''}
                onChange={set('cgpa_max')}
              />
            </div>
            <Select
              label="Verification"
              name="verified"
              value={filters.verified ?? ''}
              onChange={set('verified')}
            >
              <option value="">Any</option>
              <option value="true">Verified only</option>
              <option value="false">Not yet verified</option>
            </Select>
            <div>
              <Select
                label="Role category"
                name="category"
                value={filters.category ?? ''}
                onChange={set('category')}
                aria-describedby="category-hint"
              >
                <option value="">Any</option>
                {categories.map((category) => (
                  <option key={category.name} value={category.name}>
                    {category.name}
                  </option>
                ))}
              </Select>
              <p id="category-hint" className="mt-1 text-xs text-ink-400">
                {categories.length
                  ? 'Also narrows the job description match.'
                  : 'No categories yet: they appear as recruiters post job descriptions.'}
              </p>
            </div>

            <div className="flex gap-2 pt-1">
              <Button type="submit" className="flex-1">
                Apply
              </Button>
              <Button
                type="button"
                variant="ghost"
                onClick={() => {
                  setFilters(EMPTY_FILTERS)
                  void load(EMPTY_FILTERS)
                }}
              >
                Clear
              </Button>
            </div>
          </form>
        </Card>

        <div className="space-y-4 lg:col-span-3">
          <JdMatchCard category={applied.category ?? ''} onResults={setRanked} />

          {ranked ? <RankedResults response={ranked} onClear={() => setRanked(null)} /> : null}

          {ranked ? (
            <h2 className="pt-2 text-base font-semibold text-ink-900">All profiles you can see</h2>
          ) : null}

          {error ? <Alert tone="error">{error}</Alert> : null}

          <p className="text-sm text-ink-600">
            {loading ? 'Searching…' : `${count} profile${count === 1 ? '' : 's'}`}
          </p>

          {!loading && results.length === 0 ? (
            <EmptyState title="No profiles match">
              Try widening the filters. Students who have set their profile to hidden never appear
              here.
            </EmptyState>
          ) : null}

          {results.map((profile) => (
            <Card key={profile.id} className="p-5">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div className="min-w-0">
                  <p className="flex flex-wrap items-center gap-2">
                    <Link
                      to={`/company/students/${profile.student_id}`}
                      className="font-medium hover:underline"
                    >
                      {profile.student.full_name}
                    </Link>
                    {profile.is_verified ? <Badge tone="success">Verified</Badge> : null}
                    {profile.is_shortlisted ? <Badge tone="brand">Shortlisted</Badge> : null}
                  </p>
                  <p className="text-sm text-ink-600">
                    {profile.headline || '—'} · {profile.student.department} ·{' '}
                    {profile.student.batch}
                  </p>
                  <p className="mt-1 text-sm text-ink-400">
                    CGPA {profile.student.cgpa ?? '—'} · {profile.experience_years} yrs experience
                    {profile.education_level ? ` · ${profile.education_level}` : ''}
                  </p>
                  {profile.skills.length ? (
                    <ul className="mt-2 flex flex-wrap gap-1.5">
                      {profile.skills.slice(0, 8).map((skill) => (
                        <li
                          key={skill.id}
                          className="rounded-full bg-ink-100 px-2 py-0.5 text-xs text-ink-600"
                        >
                          {skill.name}
                        </li>
                      ))}
                    </ul>
                  ) : null}
                </div>

                <Button
                  size="sm"
                  variant={profile.is_shortlisted ? 'secondary' : 'primary'}
                  onClick={() => toggleShortlist(profile)}
                >
                  {profile.is_shortlisted ? 'Remove from shortlist' : 'Shortlist'}
                </Button>
              </div>
            </Card>
          ))}
        </div>
      </div>
    </>
  )
}

/**
 * Rank visible students against a pasted JD. The applied role category goes
 * with it, so both lists narrow the same way; one only chosen in the form
 * does not, until Apply.
 */
function JdMatchCard({
  category,
  onResults,
}: {
  category: string
  onResults: (response: MatchSearchResponse) => void
}) {
  const [jdText, setJdText] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [fieldError, setFieldError] = useState<string | null>(null)

  async function submit(event: FormEvent) {
    event.preventDefault()
    setError(null)
    setFieldError(null)
    if (jdText.trim().length < JD_MIN_CHARS) {
      setFieldError(`Paste at least ${JD_MIN_CHARS} characters of the job description.`)
      return
    }
    setBusy(true)
    try {
      onResults(await matchingApi.search(jdText, category ? { categories: category } : {}))
    } catch (caught) {
      const jdErrors = caught instanceof ApiError ? caught.fieldErrors.jd_text : undefined
      if (jdErrors?.length) setFieldError(jdErrors.join(' '))
      else setError(describeMatchingError(caught, 'Could not match against that job description.'))
    } finally {
      setBusy(false)
    }
  }

  return (
    <Card className="p-5">
      <CardTitle hint="Paste a job description to rank the students you can see by how well they match it.">
        Match against a job description
      </CardTitle>
      <form onSubmit={submit} className="space-y-3" noValidate>
        <div className="space-y-1.5">
          <label htmlFor="match-jd-text" className="block text-sm font-medium text-ink-800">
            Job description
          </label>
          <textarea
            id="match-jd-text"
            rows={5}
            value={jdText}
            onChange={(event) => setJdText(event.target.value)}
            aria-invalid={fieldError ? true : undefined}
            aria-describedby={fieldError ? 'match-jd-text-error' : undefined}
            placeholder="Backend engineer: Python, Django, PostgreSQL, 1+ years…"
            className="w-full rounded-lg border border-ink-200 px-3 py-2.5 text-sm focus:border-brand-500 focus:ring-2 focus:ring-brand-500/30 focus:outline-none"
          />
          {fieldError ? (
            <p id="match-jd-text-error" role="alert" className="text-sm text-bad-600">
              {fieldError}
            </p>
          ) : null}
        </div>
        <div className="flex flex-wrap items-center gap-3">
          <Button type="submit" loading={busy}>
            Rank students
          </Button>
          {category ? (
            <span className="text-sm text-ink-600">
              In category <strong>{category}</strong>
            </span>
          ) : null}
          <span role="status" aria-live="polite" className="text-sm text-ink-400">
            {busy ? 'Matching…' : ''}
          </span>
        </div>
        {error ? <Alert tone="error">{error}</Alert> : null}
      </form>
    </Card>
  )
}

function RankedResults({
  response,
  onClear,
}: {
  response: MatchSearchResponse
  onClear: () => void
}) {
  return (
    <section aria-labelledby="ranked-heading" className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 id="ranked-heading" className="text-base font-semibold text-ink-900">
            Ranked against your job description
          </h2>
          <p className="text-sm text-ink-600" role="status" aria-live="polite">
            {response.count} match{response.count === 1 ? '' : 'es'}
            {response.job.canonical_role ? ` · read as ${response.job.canonical_role}` : ''}
          </p>
        </div>
        <Button variant="ghost" onClick={onClear}>
          Clear the match
        </Button>
      </div>

      {response.results.length === 0 ? (
        <EmptyState title="No students match this job description">
          Only students whose profiles you can see, and who have uploaded a resume, are ranked.
        </EmptyState>
      ) : (
        <ol className="space-y-3" aria-label="Ranked students">
          {response.results.map((result, index) => (
            <RankedResult key={result.student_id} rank={index + 1} result={result} />
          ))}
        </ol>
      )}
    </section>
  )
}

function RankedResult({ rank, result }: { rank: number; result: MatchResult }) {
  const [open, setOpen] = useState(false)
  const breakdownId = `breakdown-${result.student_id}`
  return (
    <li>
      <Card className="p-5">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="min-w-0 flex-1">
            <p className="flex flex-wrap items-center gap-2">
              <span className="text-sm text-ink-400 tabular-nums">#{rank}</span>
              <Link
                to={`/company/students/${result.student_id}`}
                className="font-medium hover:underline"
              >
                {result.student.full_name}
              </Link>
              {result.is_verified ? <Badge tone="success">Verified</Badge> : null}
              {result.match.flagged ? <Badge tone="warning">Below a requirement</Badge> : null}
            </p>
            <p className="text-sm text-ink-600">
              {result.headline || '—'} · {result.student.department} · {result.student.batch}
            </p>
            {result.categories.length ? (
              <ul className="mt-2 flex flex-wrap gap-1.5" aria-label="Role categories">
                {result.categories.map((name) => (
                  <li key={name}>
                    <Badge tone="brand">{name}</Badge>
                  </li>
                ))}
              </ul>
            ) : null}
          </div>
          <div className="w-full sm:w-56">
            <ScoreBar score={result.match.score} />
          </div>
        </div>

        <div className="mt-4">
          <SkillChips match={result.match} />
        </div>

        <div className="mt-3">
          <Button
            size="sm"
            variant="ghost"
            aria-expanded={open}
            aria-controls={breakdownId}
            onClick={() => setOpen((current) => !current)}
          >
            {open ? 'Hide score breakdown' : 'Show score breakdown'}
          </Button>
          <div id={breakdownId} hidden={!open} className="mt-2">
            <MatchBreakdown match={result.match} />
          </div>
        </div>
      </Card>
    </li>
  )
}
