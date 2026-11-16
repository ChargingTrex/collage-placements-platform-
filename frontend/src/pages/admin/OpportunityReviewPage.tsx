import { useCallback, useEffect, useState } from 'react'

import { ApiError } from '@/api/client'
import { formatSalary, opportunitiesApi, type Opportunity } from '@/api/opportunities'
import { Alert, Button, Card, EmptyState, PageHeader } from '@/components/ui'

function ReviewCard({ row, onDone }: { row: Opportunity; onDone: (message: string) => void }) {
  const [rejecting, setRejecting] = useState(false)
  const [reason, setReason] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function run(action: () => Promise<unknown>, message: string) {
    setBusy(true)
    setError(null)
    try {
      await action()
      onDone(message)
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : 'That did not work.')
    } finally {
      setBusy(false)
    }
  }

  function reject() {
    // The recruiter sees this text, so an empty reason is refused here and on the server.
    if (!reason.trim()) {
      setError('Give a reason so the recruiter knows what to change.')
      return
    }
    void run(() => opportunitiesApi.reject(row.id, reason.trim()), `Rejected “${row.title}”.`)
  }

  return (
    <Card className="space-y-3">
      <div>
        <h2 className="text-base font-semibold">{row.title}</h2>
        <p className="text-sm text-ink-600">
          {row.company_name ?? row.company} ·{' '}
          {row.role_type === 'internship' ? 'Internship' : 'Full time'} · Deadline {row.deadline} ·{' '}
          {formatSalary(row)}
        </p>
      </div>
      <p className="max-h-40 overflow-y-auto text-sm whitespace-pre-wrap text-ink-800">
        {row.description}
      </p>
      <p className="text-sm text-ink-600">
        Skills: {row.required_skills.join(', ') || '—'} · Departments:{' '}
        {row.eligible_departments.join(', ') || 'all'} · Minimum CGPA: {row.min_cgpa ?? '—'}
      </p>

      {error ? <Alert tone="error">{error}</Alert> : null}

      {rejecting ? (
        <div className="space-y-2">
          <label htmlFor={`reason-${row.id}`} className="block text-sm font-medium text-ink-800">
            Reason for rejecting
          </label>
          <textarea
            id={`reason-${row.id}`}
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            rows={3}
            className="w-full rounded-lg border border-ink-200 bg-white px-3 py-2.5 text-sm focus:border-brand-500 focus:ring-2 focus:ring-brand-500/30 focus:outline-none"
          />
          <div className="flex gap-2">
            <Button size="sm" variant="danger" loading={busy} onClick={reject}>
              Confirm reject
            </Button>
            <Button size="sm" variant="ghost" onClick={() => setRejecting(false)}>
              Cancel
            </Button>
          </div>
        </div>
      ) : (
        <div className="flex gap-2">
          <Button
            size="sm"
            loading={busy}
            onClick={() =>
              void run(() => opportunitiesApi.approve(row.id), `Approved “${row.title}”.`)
            }
          >
            Approve
          </Button>
          <Button size="sm" variant="secondary" onClick={() => setRejecting(true)}>
            Reject
          </Button>
        </div>
      )}
    </Card>
  )
}

export default function OpportunityReviewPage() {
  const [rows, setRows] = useState<Opportunity[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)

  const load = useCallback(async () => {
    try {
      setRows(await opportunitiesApi.list({ status: 'pending_review' }))
      setError(null)
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : 'Could not load the queue.')
    }
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  return (
    <>
      <PageHeader
        title="Review queue"
        subtitle="Recruiter postings wait here until you approve them."
      />
      {error ? (
        <div className="mb-4">
          <Alert tone="error">{error}</Alert>
        </div>
      ) : null}
      {notice ? (
        <div className="mb-4">
          <Alert tone="success">{notice}</Alert>
        </div>
      ) : null}
      {rows === null && !error ? (
        <p className="py-8 text-center text-sm text-ink-400">Loading…</p>
      ) : rows && rows.length === 0 ? (
        <EmptyState title="Nothing waiting for review" />
      ) : (
        <ul className="space-y-4" aria-label="Postings awaiting review">
          {rows?.map((row) => (
            <li key={row.id}>
              <ReviewCard
                row={row}
                onDone={(message) => {
                  setNotice(message)
                  void load()
                }}
              />
            </li>
          ))}
        </ul>
      )}
    </>
  )
}
