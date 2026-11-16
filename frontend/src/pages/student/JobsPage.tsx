import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'

import { ApiError } from '@/api/client'
import { opportunitiesApi, type FeedRow } from '@/api/opportunities'
import JobCard from '@/components/JobCard'
import { Alert, EmptyState, Field, PageHeader } from '@/components/ui'

export default function JobsPage() {
  const [rows, setRows] = useState<FeedRow[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [search, setSearch] = useState('')

  useEffect(() => {
    let cancelled = false
    opportunitiesApi
      .feed()
      .then((next) => !cancelled && setRows(next))
      .catch((caught) => {
        if (!cancelled)
          setError(caught instanceof ApiError ? caught.message : 'Could not load the jobs.')
      })
    return () => {
      cancelled = true
    }
  }, [])

  const shown = useMemo(() => {
    if (!rows) return null
    const needle = search.trim().toLowerCase()
    if (!needle) return rows
    return rows.filter((row) =>
      `${row.title} ${row.company_name ?? ''} ${row.required_skills.join(' ')}`
        .toLowerCase()
        .includes(needle),
    )
  }, [rows, search])

  return (
    <>
      <PageHeader
        title="Jobs and internships"
        subtitle="Ranked by how well your profile and resume read against each posting."
      />
      <p className="mb-4 text-sm text-ink-600">
        Applying needs a resume on your profile.{' '}
        <Link to="/student/profile" className="font-medium underline">
          Open my profile
        </Link>
      </p>
      <div className="mb-4 max-w-sm">
        <Field
          label="Search"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Title, company or skill"
        />
      </div>
      {error ? <Alert tone="error">{error}</Alert> : null}
      {shown === null && !error ? (
        <p className="py-8 text-center text-sm text-ink-400">Loading…</p>
      ) : shown && shown.length === 0 ? (
        <EmptyState title="Nothing to show">No open postings match right now.</EmptyState>
      ) : (
        <ul className="space-y-4" aria-label="Open postings">
          {shown?.map((row) => (
            <li key={row.id}>
              <JobCard
                row={row}
                onApplied={(id, status) =>
                  setRows((current) =>
                    current
                      ? current.map((r) =>
                          r.id === id
                            ? {
                                ...r,
                                has_applied: true,
                                application_status: status,
                              }
                            : r,
                        )
                      : current,
                  )
                }
              />
            </li>
          ))}
        </ul>
      )}
    </>
  )
}
