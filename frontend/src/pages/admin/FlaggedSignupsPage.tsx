import { useEffect, useState } from 'react'

import { ApiError } from '@/api/client'
import { rosterApi, type FlaggedSignup, type FlagStatus } from '@/api/roster'
import { Alert, Badge, Button, Card, EmptyState, PageHeader } from '@/components/ui'

const FILTERS: Array<{ value: FlagStatus | ''; label: string }> = [
  { value: 'open', label: 'Open' },
  { value: 'resolved', label: 'Resolved' },
  { value: 'dismissed', label: 'Dismissed' },
  { value: '', label: 'All' },
]

const STATUS_TONE = {
  open: 'warning',
  resolved: 'success',
  dismissed: 'neutral',
} as const

export default function FlaggedSignupsPage() {
  const [items, setItems] = useState<FlaggedSignup[]>([])
  const [status, setStatus] = useState<FlagStatus | ''>('open')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [busyId, setBusyId] = useState<string | null>(null)
  const [notes, setNotes] = useState<Record<string, string>>({})

  async function load(next: FlagStatus | '' = status) {
    setLoading(true)
    setError(null)
    try {
      const page = await rosterApi.flagged(next ? { status: next } : {})
      setItems(page.results)
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : 'Could not load flagged signups.')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void load(status)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [status])

  async function review(item: FlaggedSignup, decision: 'resolved' | 'dismissed') {
    setBusyId(item.id)
    setError(null)
    try {
      await rosterApi.review(item.id, decision, notes[item.id] ?? '')
      await load()
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : 'Could not record that decision.')
    } finally {
      setBusyId(null)
    }
  }

  return (
    <>
      <PageHeader
        title="Flagged signups"
        subtitle="Attempts that failed roster matching. Every one is blocked from creating an account until you act."
      />

      <div className="mb-4 flex flex-wrap gap-1 rounded-lg bg-ink-100 p-1 sm:inline-flex">
        {FILTERS.map((filter) => (
          <button
            key={filter.label}
            type="button"
            onClick={() => setStatus(filter.value)}
            className={`rounded-md px-3 py-1.5 text-sm font-medium transition ${
              status === filter.value ? 'bg-white text-ink-900 shadow-sm' : 'text-ink-600 hover:text-ink-800'
            }`}
          >
            {filter.label}
          </button>
        ))}
      </div>

      {error ? (
        <div className="mb-4">
          <Alert tone="error">{error}</Alert>
        </div>
      ) : null}

      {loading ? (
        <p className="py-8 text-center text-sm text-ink-400">Loading…</p>
      ) : items.length === 0 ? (
        <EmptyState title="Nothing flagged">
          Signup attempts that don't match the roster will appear here.
        </EmptyState>
      ) : (
        <div className="space-y-3">
          {items.map((item) => (
            <Card key={item.id} className="p-4">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <p className="font-mono text-sm">{item.prn}</p>
                  <p className="text-sm text-ink-600">{item.email}</p>
                  <p className="mt-1 text-sm text-ink-800">{item.reason_display}</p>
                </div>
                <div className="flex items-center gap-2">
                  {item.attempts > 1 ? <Badge tone="warning">{item.attempts} attempts</Badge> : null}
                  <Badge tone={STATUS_TONE[item.status]}>{item.status}</Badge>
                </div>
              </div>

              {item.status === 'open' ? (
                <div className="mt-4 flex flex-wrap items-end gap-2">
                  <input
                    aria-label={`Note for ${item.prn}`}
                    placeholder="Note (optional)"
                    value={notes[item.id] ?? ''}
                    onChange={(event) =>
                      setNotes((current) => ({ ...current, [item.id]: event.target.value }))
                    }
                    className="min-w-48 flex-1 rounded-lg border border-ink-200 px-3 py-2 text-sm focus:border-brand-500 focus:ring-2 focus:ring-brand-500/30 focus:outline-none"
                  />
                  <Button
                    size="sm"
                    loading={busyId === item.id}
                    onClick={() => review(item, 'resolved')}
                  >
                    Resolve
                  </Button>
                  <Button
                    size="sm"
                    variant="secondary"
                    loading={busyId === item.id}
                    onClick={() => review(item, 'dismissed')}
                  >
                    Dismiss
                  </Button>
                </div>
              ) : item.admin_note ? (
                <p className="mt-3 text-sm text-ink-600">
                  <span className="font-medium text-ink-800">Note:</span> {item.admin_note}
                  {item.reviewed_by_email ? ` — ${item.reviewed_by_email}` : null}
                </p>
              ) : null}
            </Card>
          ))}
        </div>
      )}
    </>
  )
}
