import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'

import { downloadFile } from '@/api/documents'
import { ApiError } from '@/api/client'
import {
  careerPathLabel,
  profilesApi,
  type AdminProfile,
  type CareerPath,
  type Outcomes,
} from '@/api/profiles'
import BarList, { type Bar } from '@/components/BarList'
import { Alert, Badge, Button, Card, CardTitle, EmptyState, Field, PageHeader } from '@/components/ui'

/**
 * Where graduating students are headed, by school. For the placement cell only.
 *
 * Read top to bottom: the bars answer "what is the shape of this batch" at a
 * glance, the cross-tab carries the exact per-school numbers, and the people
 * table at the bottom is for finding an individual. Clicking a bar narrows
 * that table, so the glance and the detail are the same question at two
 * depths rather than two unrelated views.
 */
export default function OutcomesPage() {
  const [batch, setBatch] = useState('')
  /** The batch the charts below are actually showing; the people table follows it. */
  const [appliedBatch, setAppliedBatch] = useState('')
  const [data, setData] = useState<Outcomes | null>(null)
  const [loading, setLoading] = useState(true)
  const [exporting, setExporting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const [path, setPath] = useState<CareerPath | null>(null)
  const [school, setSchool] = useState<string | null>(null)

  const load = useCallback(async (batchFilter: string) => {
    setLoading(true)
    setError(null)
    try {
      setData(await profilesApi.outcomes(batchFilter.trim() || undefined))
      setAppliedBatch(batchFilter.trim())
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : 'Could not load outcomes.')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void load('')
  }, [load])

  async function exportCsv() {
    setExporting(true)
    setError(null)
    const filter = batch.trim() || undefined
    try {
      // A bearer fetch, not a bare link: the export endpoint needs the token.
      await downloadFile(
        profilesApi.outcomesExportUrl(filter),
        filter ? `outcomes-${filter}.csv` : 'outcomes.csv',
      )
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Could not export.')
    } finally {
      setExporting(false)
    }
  }

  // Biggest first: the point of the glance is which paths dominate, and the
  // server's order is the enum's, which says nothing about size.
  const pathBars: Bar[] = useMemo(
    () =>
      (data?.paths ?? [])
        .map((p) => ({ key: p.value, label: p.label, value: data?.totals[p.value] ?? 0 }))
        .sort((a, b) => b.value - a.value),
    [data],
  )

  const schoolBars: Bar[] = useMemo(
    () =>
      (data?.rows ?? [])
        .map((row) => ({ key: row.school, label: row.school_name, value: row.total }))
        .sort((a, b) => b.value - a.value),
    [data],
  )

  const schoolName = (key: string) =>
    data?.rows.find((row) => row.school === key)?.school_name ?? key

  return (
    <>
      <PageHeader
        title="Career outcomes"
        subtitle="What students on the roster plan to do after graduation, by school."
      />

      <form
        className="mb-4 flex flex-wrap items-end gap-2"
        onSubmit={(event) => {
          event.preventDefault()
          void load(batch)
        }}
      >
        <div className="w-40">
          <Field
            label="Batch"
            name="batch"
            inputMode="numeric"
            placeholder="All batches"
            value={batch}
            onChange={(event) => setBatch(event.target.value)}
          />
        </div>
        <Button type="submit" variant="secondary">
          Apply
        </Button>
        <Button type="button" variant="secondary" loading={exporting} onClick={() => void exportCsv()}>
          Export CSV
        </Button>
      </form>

      {error ? (
        <div className="mb-4">
          <Alert tone="error">{error}</Alert>
        </div>
      ) : null}

      {loading ? (
        <p className="py-8 text-center text-sm text-ink-400">Loading…</p>
      ) : !data || data.grand_total === 0 ? (
        <EmptyState title="No students counted">
          Students appear here once they have signed up.
        </EmptyState>
      ) : (
        <>
          <div className="mb-4 grid gap-4 sm:grid-cols-3">
            {[
              ['Students', data.grand_total],
              ['Verified profiles', data.verified],
              ['Also attending placements', data.also_attending_placements],
            ].map(([label, value]) => (
              <Card key={String(label)} className="p-4">
                <p className="text-2xl font-semibold tabular-nums">{value}</p>
                <p className="text-sm text-ink-600">{label}</p>
              </Card>
            ))}
          </div>

          {/* At a glance. Clicking a bar filters the people table below. */}
          {/* Side by side only once there is room for both label columns;
              below that they stack full width rather than squeeze. */}
          <div className="mb-6 grid gap-4 xl:grid-cols-2">
            <Card className="p-5">
              <CardTitle hint="Click a bar to list those students below.">
                Career paths
              </CardTitle>
              <BarList
                bars={pathBars}
                total={data.grand_total}
                selectedKey={path}
                onSelect={(key) => setPath(key as CareerPath | null)}
              />
            </Card>

            <Card className="p-5">
              <CardTitle hint="Click a bar to list those students below.">
                Students by school
              </CardTitle>
              <BarList
                bars={schoolBars}
                total={data.grand_total}
                selectedKey={school}
                onSelect={setSchool}
              />
            </Card>
          </div>

          <h2 className="mb-2 text-sm font-semibold tracking-wide text-ink-600 uppercase">
            Every school and path
          </h2>
          <div className="mb-8 overflow-x-auto rounded-xl border border-ink-200 bg-white">
            <table className="w-full text-sm">
              <caption className="sr-only">Students by school and career path</caption>
              <thead>
                <tr className="border-b border-ink-200 text-left">
                  <th scope="col" className="px-3 py-2 font-medium">
                    School
                  </th>
                  {data.paths.map((p) => (
                    <th key={p.value} scope="col" className="px-3 py-2 text-right font-medium">
                      {p.label}
                    </th>
                  ))}
                  <th scope="col" className="px-3 py-2 text-right font-medium">
                    Total
                  </th>
                </tr>
              </thead>
              <tbody>
                {data.rows.map((row) => (
                  <tr key={row.school} className="border-b border-ink-100">
                    <th scope="row" className="px-3 py-2 text-left font-normal">
                      {row.school_name}
                    </th>
                    {data.paths.map((p) => (
                      <td key={p.value} className="px-3 py-2 text-right tabular-nums">
                        {row.counts[p.value] ?? 0}
                      </td>
                    ))}
                    <td className="px-3 py-2 text-right font-medium tabular-nums">{row.total}</td>
                  </tr>
                ))}
              </tbody>
              <tfoot>
                <tr className="font-semibold">
                  <th scope="row" className="px-3 py-2 text-left">
                    Total
                  </th>
                  {data.paths.map((p) => (
                    <td key={p.value} className="px-3 py-2 text-right tabular-nums">
                      {data.totals[p.value] ?? 0}
                    </td>
                  ))}
                  <td className="px-3 py-2 text-right tabular-nums">{data.grand_total}</td>
                </tr>
              </tfoot>
            </table>
          </div>

          <PeopleTable
            batch={appliedBatch}
            path={path}
            school={school}
            schoolName={schoolName}
            onClearPath={() => setPath(null)}
            onClearSchool={() => setSchool(null)}
          />
        </>
      )}
    </>
  )
}

/**
 * The individual students behind the bars, searchable by name, PRN or email.
 *
 * Its own fetch rather than a slice of the outcomes payload: that one is
 * counts only, deliberately, so the dashboard stays one cheap query however
 * large the roster gets.
 */
function PeopleTable({
  batch,
  path,
  school,
  schoolName,
  onClearPath,
  onClearSchool,
}: {
  batch: string
  path: CareerPath | null
  school: string | null
  schoolName: (key: string) => string
  onClearPath: () => void
  onClearSchool: () => void
}) {
  const [search, setSearch] = useState('')
  /** Only sent on submit, so a half-typed name does not fire a request a letter. */
  const [applied, setApplied] = useState('')
  const [page, setPage] = useState(1)
  const [rows, setRows] = useState<AdminProfile[]>([])
  const [count, setCount] = useState(0)
  const [hasNext, setHasNext] = useState(false)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let live = true
    setLoading(true)
    setError(null)
    profilesApi
      .adminList({
        search: applied || undefined,
        career_path: path ?? undefined,
        school: school ?? undefined,
        batch: batch || undefined,
        page,
      })
      .then((data) => {
        if (!live) return
        setRows(data.results)
        setCount(data.count)
        setHasNext(Boolean(data.next))
      })
      .catch((caught) => {
        if (!live) return
        setError(caught instanceof ApiError ? caught.message : 'Could not load students.')
      })
      .finally(() => {
        if (live) setLoading(false)
      })
    return () => {
      live = false
    }
  }, [applied, path, school, batch, page])

  // Any change of filter starts again at the first page, or an empty page 3
  // would read as "no such students".
  useEffect(() => {
    setPage(1)
  }, [applied, path, school, batch])

  return (
    <>
      <h2 className="mb-2 text-sm font-semibold tracking-wide text-ink-600 uppercase">
        Students
      </h2>

      <form
        className="mb-3 flex flex-wrap items-end gap-2"
        onSubmit={(event) => {
          event.preventDefault()
          setApplied(search.trim())
        }}
      >
        <div className="w-72">
          <Field
            label="Search"
            name="people_search"
            placeholder="Name, PRN or email"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
          />
        </div>
        <Button type="submit" variant="secondary">
          Search
        </Button>
        {applied ? (
          <Button
            type="button"
            variant="ghost"
            onClick={() => {
              setSearch('')
              setApplied('')
            }}
          >
            Clear
          </Button>
        ) : null}
      </form>

      {path || school ? (
        <div className="mb-3 flex flex-wrap items-center gap-2 text-sm">
          <span className="text-ink-600">Filtered to</span>
          {path ? (
            <button
              type="button"
              onClick={onClearPath}
              className="rounded-full bg-brand-50 px-3 py-1 text-brand-700 transition hover:bg-brand-100"
            >
              {careerPathLabel(path)} ✕
            </button>
          ) : null}
          {school ? (
            <button
              type="button"
              onClick={onClearSchool}
              className="rounded-full bg-brand-50 px-3 py-1 text-brand-700 transition hover:bg-brand-100"
            >
              {schoolName(school)} ✕
            </button>
          ) : null}
        </div>
      ) : null}

      {error ? (
        <div className="mb-3">
          <Alert tone="error">{error}</Alert>
        </div>
      ) : null}

      {loading && !rows.length ? (
        <p className="py-8 text-center text-sm text-ink-400">Loading…</p>
      ) : !rows.length ? (
        <EmptyState title="No students match">
          Clear the search or the filters above.
        </EmptyState>
      ) : (
        /* On a refetch the previous rows stay put, dimmed: clicking a bar
           should not collapse the table and jump the page. */
        <div aria-busy={loading} className={loading ? 'opacity-60 transition-opacity' : undefined}>
          <div className="overflow-x-auto rounded-xl border border-ink-200 bg-white">
            <table className="w-full text-sm">
              <caption className="sr-only">Students matching the current filters</caption>
              <thead>
                <tr className="border-b border-ink-200 text-left">
                  {['Name', 'PRN', 'School', 'Career path', 'CGPA', ''].map((heading, index) => (
                    <th
                      key={heading || index}
                      scope="col"
                      className={`px-3 py-2 font-medium ${heading === 'CGPA' ? 'text-right' : ''}`}
                    >
                      {heading}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {rows.map((row) => (
                  <tr key={row.student_id} className="border-b border-ink-100">
                    <th scope="row" className="px-3 py-2 text-left font-normal">
                      <Link
                        className="text-brand-600 hover:underline"
                        to={`/admin/profiles/${row.student_id}`}
                      >
                        {row.student.full_name}
                      </Link>
                    </th>
                    <td className="px-3 py-2 tabular-nums">{row.student.prn}</td>
                    <td className="px-3 py-2">{row.student.school || '—'}</td>
                    <td className="px-3 py-2">{careerPathLabel(row.career_path)}</td>
                    <td className="px-3 py-2 text-right tabular-nums">
                      {row.student.cgpa ?? '—'}
                    </td>
                    <td className="px-3 py-2">
                      {row.is_verified ? <Badge tone="success">Verified</Badge> : null}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="mt-3 flex items-center justify-between text-sm text-ink-600">
            <span>
              {count} student{count === 1 ? '' : 's'}
            </span>
            <span className="flex items-center gap-2">
              <Button
                type="button"
                variant="secondary"
                size="sm"
                disabled={page === 1}
                onClick={() => setPage((current) => current - 1)}
              >
                Previous
              </Button>
              <span className="tabular-nums">Page {page}</span>
              <Button
                type="button"
                variant="secondary"
                size="sm"
                disabled={!hasNext}
                onClick={() => setPage((current) => current + 1)}
              >
                Next
              </Button>
            </span>
          </div>
        </div>
      )}
    </>
  )
}
