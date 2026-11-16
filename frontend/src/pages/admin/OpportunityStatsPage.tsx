import { useEffect, useState } from 'react'

import { ApiError } from '@/api/client'
import { opportunitiesApi, type OpportunityStats } from '@/api/opportunities'
import { Alert, Card, CardTitle, PageHeader } from '@/components/ui'

function Counts({ title, counts }: { title: string; counts: Record<string, number> }) {
  const entries = Object.entries(counts)
  return (
    <Card>
      <CardTitle>{title}</CardTitle>
      {entries.length === 0 ? (
        <p className="text-sm text-ink-400">Nothing yet.</p>
      ) : (
        <dl className="grid grid-cols-2 gap-2 text-sm">
          {entries.map(([name, count]) => (
            <div key={name} className="flex justify-between">
              <dt className="text-ink-600">{name.replace(/_/g, ' ')}</dt>
              <dd className="font-medium tabular-nums">{count}</dd>
            </div>
          ))}
        </dl>
      )}
    </Card>
  )
}

export default function OpportunityStatsPage() {
  const [stats, setStats] = useState<OpportunityStats | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    opportunitiesApi
      .stats()
      .then((next) => !cancelled && setStats(next))
      .catch((caught) => {
        if (!cancelled) setError(caught instanceof ApiError ? caught.message : 'Could not load the figures.')
      })
    return () => {
      cancelled = true
    }
  }, [])

  return (
    <>
      <PageHeader title="Opportunity figures" />
      {error ? <Alert tone="error">{error}</Alert> : null}
      {!stats && !error ? <p className="py-8 text-center text-sm text-ink-400">Loading…</p> : null}
      {stats ? (
        <div className="space-y-4">
          <div className="grid gap-4 sm:grid-cols-2">
            <Counts title="Postings by status" counts={stats.opportunities_by_status} />
            <Counts title="Applications by status" counts={stats.applications_by_status} />
          </div>
          <Card>
            <CardTitle>Median time to shortlist</CardTitle>
            <p className="text-3xl font-semibold tabular-nums">
              {stats.median_hours_to_shortlist === null
                ? '—'
                : `${stats.median_hours_to_shortlist.toFixed(1)} hours`}
            </p>
            {stats.median_hours_to_shortlist === null ? (
              <p className="mt-1 text-sm text-ink-400">No application has been shortlisted yet.</p>
            ) : null}
          </Card>
          <Card>
            <CardTitle>Per posting</CardTitle>
            <table className="w-full text-sm">
              <caption className="sr-only">Applicants per posting</caption>
              <thead>
                <tr className="text-left text-xs text-ink-400">
                  <th scope="col" className="pb-1 font-medium">Posting</th>
                  <th scope="col" className="pb-1 font-medium">Company</th>
                  <th scope="col" className="pb-1 text-right font-medium">Applicants</th>
                  <th scope="col" className="pb-1 font-medium">By status</th>
                </tr>
              </thead>
              <tbody>
                {stats.per_opportunity.map((row) => (
                  <tr key={row.id} className="border-t border-ink-100">
                    <td className="py-1.5">{row.title}</td>
                    <td className="py-1.5">{row.company}</td>
                    <td className="py-1.5 text-right tabular-nums">{row.applicants}</td>
                    <td className="py-1.5 text-ink-600">
                      {Object.entries(row.by_status).map(([k, v]) => `${k.replace(/_/g, ' ')} ${v}`).join(', ') || '—'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Card>
        </div>
      ) : null}
    </>
  )
}
