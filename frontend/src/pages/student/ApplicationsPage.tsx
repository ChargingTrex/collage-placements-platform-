import { useEffect, useState } from 'react'

import type { Collected } from '@/api/paginate'
import { ApiError } from '@/api/client'
import {
  APPLICATION_STATUS_LABEL,
  opportunitiesApi,
  WITHDRAWABLE,
  type StudentApplication,
} from '@/api/opportunities'
import { ApplicationStatusBadge } from '@/components/StatusBadges'
import TruncationNote from '@/components/TruncationNote'
import { Alert, Button, Card, EmptyState, PageHeader } from '@/components/ui'

function when(iso: string): string {
  const date = new Date(iso)
  return Number.isNaN(date.getTime()) ? iso : date.toLocaleDateString('en-IN')
}

function ApplicationCard({
  application,
  onChanged,
}: {
  application: StudentApplication
  onChanged: (next: StudentApplication) => void
}) {
  const [confirming, setConfirming] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function withdraw() {
    setBusy(true)
    setError(null)
    try {
      onChanged(await opportunitiesApi.withdraw(application.id))
      setConfirming(false)
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : 'Could not withdraw.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <Card className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        <h2 className="text-base font-semibold">{application.opportunity.title}</h2>
        <ApplicationStatusBadge status={application.status} />
      </div>
      <p className="text-sm text-ink-600">Applied {when(application.applied_at)}</p>

      <ol aria-label="History" className="space-y-1 border-l border-ink-200 pl-4 text-sm">
        {application.events.map((event, index) => (
          <li key={`${event.created_at}-${index}`}>
            <span className="font-medium">{APPLICATION_STATUS_LABEL[event.to_status]}</span>{' '}
            <span className="text-ink-400">{when(event.created_at)}</span>
            {event.note ? <span className="text-ink-600"> · {event.note}</span> : null}
          </li>
        ))}
      </ol>

      {error ? <Alert tone="error">{error}</Alert> : null}

      {WITHDRAWABLE.includes(application.status) ? (
        confirming ? (
          <div className="flex items-center gap-2">
            <span className="text-sm text-ink-600">Withdraw this application?</span>
            <Button size="sm" variant="danger" loading={busy} onClick={() => void withdraw()}>
              Confirm withdraw
            </Button>
            <Button size="sm" variant="ghost" onClick={() => setConfirming(false)}>
              Keep it
            </Button>
          </div>
        ) : (
          <Button size="sm" variant="secondary" onClick={() => setConfirming(true)}>
            Withdraw
          </Button>
        )
      ) : null}
    </Card>
  )
}

export default function ApplicationsPage() {
  const [rows, setRows] = useState<StudentApplication[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [cut, setCut] = useState<Collected<unknown> | null>(null)

  useEffect(() => {
    let cancelled = false
    opportunitiesApi
      .myApplications()
      .then((next) => {
        if (cancelled) return
        setRows(next.rows)
        setCut(next)
      })
      .catch((caught) => {
        if (!cancelled)
          setError(
            caught instanceof ApiError ? caught.message : 'Could not load your applications.',
          )
      })
    return () => {
      cancelled = true
    }
  }, [])

  return (
    <>
      <PageHeader title="My applications" subtitle="Where each application stands." />
      <TruncationNote collected={cut} />
      {error ? <Alert tone="error">{error}</Alert> : null}
      {rows === null && !error ? (
        <p className="py-8 text-center text-sm text-ink-400">Loading…</p>
      ) : rows && rows.length === 0 ? (
        <EmptyState title="No applications yet">Find something on the Jobs page.</EmptyState>
      ) : (
        <ul className="space-y-4" aria-label="Your applications">
          {rows?.map((application) => (
            <li key={application.id}>
              <ApplicationCard
                application={application}
                onChanged={(next) =>
                  setRows(
                    (current) => current?.map((r) => (r.id === next.id ? next : r)) ?? current,
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
