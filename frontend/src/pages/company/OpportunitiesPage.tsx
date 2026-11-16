import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'

import { ApiError } from '@/api/client'
import { formatSalary, opportunitiesApi, type Opportunity } from '@/api/opportunities'
import OpportunityForm from '@/components/OpportunityForm'
import { OpportunityStatusBadge } from '@/components/StatusBadges'
import { Alert, Button, Card, EmptyState, PageHeader } from '@/components/ui'

export default function OpportunitiesPage() {
  const [rows, setRows] = useState<Opportunity[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [editing, setEditing] = useState<Opportunity | 'new' | null>(null)
  const [busyId, setBusyId] = useState<string | null>(null)

  const load = useCallback(async () => {
    try {
      setRows(await opportunitiesApi.list())
      setError(null)
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : 'Could not load your postings.')
    }
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  async function act(id: string, run: () => Promise<unknown>, done: string) {
    setBusyId(id)
    setNotice(null)
    setError(null)
    try {
      await run()
      setNotice(done)
      await load()
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : 'That did not work.')
    } finally {
      setBusyId(null)
    }
  }

  if (editing) {
    return (
      <>
        <PageHeader title={editing === 'new' ? 'New posting' : 'Edit posting'} />
        <Card>
          <OpportunityForm
            initial={editing === 'new' ? undefined : editing}
            onCancel={() => setEditing(null)}
            onSaved={() => {
              setEditing(null)
              setNotice('Saved. Submit it for review when it is ready.')
              void load()
            }}
          />
        </Card>
      </>
    )
  }

  return (
    <>
      <PageHeader
        title="My postings"
        subtitle="New postings are reviewed by the placement cell before students see them."
      />
      <div className="mb-4 flex justify-end">
        <Button onClick={() => setEditing('new')}>New posting</Button>
      </div>
      {error ? <div className="mb-4"><Alert tone="error">{error}</Alert></div> : null}
      {notice ? <div className="mb-4"><Alert tone="success">{notice}</Alert></div> : null}

      {rows === null ? (
        <p className="py-8 text-center text-sm text-ink-400">Loading…</p>
      ) : rows.length === 0 ? (
        <EmptyState title="No postings yet">Create one to start receiving applications.</EmptyState>
      ) : (
        <ul className="space-y-3">
          {rows.map((row) => (
            <li key={row.id}>
              <Card className="space-y-3">
                <div className="flex flex-wrap items-center gap-2">
                  <h2 className="text-base font-semibold">{row.title}</h2>
                  <OpportunityStatusBadge status={row.status} />
                </div>
                <p className="text-sm text-ink-600">
                  {row.role_type === 'internship' ? 'Internship' : 'Full time'} · Deadline {row.deadline} ·{' '}
                  {row.openings} opening{row.openings === 1 ? '' : 's'} · {formatSalary(row)}
                </p>
                {row.status === 'rejected' && row.rejection_reason ? (
                  <Alert tone="error" title="Rejected by the placement cell">
                    {row.rejection_reason}
                  </Alert>
                ) : null}
                {row.status === 'pending_review' ? (
                  <p className="text-sm text-ink-600">Waiting for the placement cell to review it.</p>
                ) : null}
                <div className="flex flex-wrap gap-2">
                  {row.status === 'draft' || row.status === 'rejected' ? (
                    <>
                      <Button size="sm" variant="secondary" onClick={() => setEditing(row)}>
                        Edit
                      </Button>
                      <Button
                        size="sm"
                        loading={busyId === row.id}
                        onClick={() =>
                          void act(row.id, () => opportunitiesApi.submit(row.id), 'Submitted for review.')
                        }
                      >
                        Submit for review
                      </Button>
                    </>
                  ) : null}
                  {row.status === 'draft' ? (
                    <Button
                      size="sm"
                      variant="danger"
                      loading={busyId === row.id}
                      onClick={() =>
                        void act(row.id, () => opportunitiesApi.remove(row.id), 'Draft deleted.')
                      }
                    >
                      Delete draft
                    </Button>
                  ) : null}
                  {row.status === 'open' ? (
                    <Button
                      size="sm"
                      variant="secondary"
                      loading={busyId === row.id}
                      onClick={() =>
                        void act(row.id, () => opportunitiesApi.close(row.id), 'Posting closed.')
                      }
                    >
                      Close
                    </Button>
                  ) : null}
                  {row.status === 'open' || row.status === 'closed' ? (
                    <Link
                      to={`/company/opportunities/${row.id}/applicants`}
                      className="inline-flex items-center rounded-lg px-3 py-1.5 text-sm font-medium text-brand-700 ring-1 ring-ink-200 hover:bg-ink-50"
                    >
                      Applicants
                    </Link>
                  ) : null}
                </div>
              </Card>
            </li>
          ))}
        </ul>
      )}
    </>
  )
}
