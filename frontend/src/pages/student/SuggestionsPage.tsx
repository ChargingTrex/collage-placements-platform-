import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'

import { ApiError } from '@/api/client'
import { opportunitiesApi, type SuggestionsResponse } from '@/api/opportunities'
import JobCard from '@/components/JobCard'
import { Alert, EmptyState, PageHeader } from '@/components/ui'

export default function SuggestionsPage() {
  const [data, setData] = useState<SuggestionsResponse | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    opportunitiesApi
      .suggestions()
      .then((next) => !cancelled && setData(next))
      .catch((caught) => {
        if (!cancelled) {
          setError(
            caught instanceof ApiError && caught.status === 429
              ? 'Suggestions are being worked out for many students right now. Try again in a minute.'
              : caught instanceof ApiError
                ? caught.message
                : 'Could not load suggestions.',
          )
        }
      })
    return () => {
      cancelled = true
    }
  }, [])

  return (
    <>
      <PageHeader
        title="Suggestions"
        subtitle="Open postings whose description reads close to your profile and resume."
      />
      <p className="mb-4 text-sm text-ink-600">
        The score is a guide to how well your resume reads against a posting. It is not a
        prediction of whether you will be selected, so read the posting and decide for yourself.
      </p>
      {error ? <Alert tone="error">{error}</Alert> : null}
      {data === null && !error ? (
        <p className="py-8 text-center text-sm text-ink-400">Loading…</p>
      ) : null}

      {data && data.results.length === 0 ? (
        data.reason === 'no_open_postings' ? (
          <EmptyState title="Nothing has been posted yet">
            There are no open postings at the moment. New ones will show up here and in your
            notifications.
          </EmptyState>
        ) : (
          <EmptyState title="Nothing fits you well right now">
            There {data.open_count === 1 ? 'is 1 open posting' : `are ${data.open_count} open postings`},
            but none reads close enough to your profile to suggest.{' '}
            <Link to="/student/jobs" className="font-medium underline">
              See all open jobs
            </Link>
          </EmptyState>
        )
      ) : null}

      {data && data.results.length > 0 ? (
        <ul className="space-y-4" aria-label="Suggested postings">
          {data.results.map((row) => (
            <li key={row.id}>
              <JobCard
                row={row}
                onApplied={(id, status) =>
                  setData((current) =>
                    current
                      ? {
                          ...current,
                          results: current.results.map((r) =>
                            r.id === id ? { ...r, has_applied: true, application_status: status } : r,
                          ),
                        }
                      : current,
                  )
                }
              />
            </li>
          ))}
        </ul>
      ) : null}
    </>
  )
}
