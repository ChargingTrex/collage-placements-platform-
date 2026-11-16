import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'

import { ApiError } from '@/api/client'
import {
  OPPORTUNITY_STATUS_LABEL,
  opportunitiesApi,
  type Opportunity,
  type OpportunityStatus,
  type RoleType,
} from '@/api/opportunities'
import OpportunityForm from '@/components/OpportunityForm'
import { OpportunityStatusBadge } from '@/components/StatusBadges'
import { Alert, Button, Card, EmptyState, Field, PageHeader, Select } from '@/components/ui'

export default function AllOpportunitiesPage() {
  const [rows, setRows] = useState<Opportunity[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [status, setStatus] = useState<OpportunityStatus | ''>('')
  const [roleType, setRoleType] = useState<RoleType | ''>('')
  const [companyId, setCompanyId] = useState('')
  const [search, setSearch] = useState('')
  const [editing, setEditing] = useState<Opportunity | 'new' | null>(null)

  const load = useCallback(async () => {
    try {
      setRows(
        await opportunitiesApi.list({
          status,
          role_type: roleType,
          company_id: companyId.trim(),
          search: search.trim(),
        }),
      )
      setError(null)
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : 'Could not load the postings.')
    }
  }, [status, roleType, companyId, search])

  useEffect(() => {
    void load()
  }, [load])

  async function close(row: Opportunity) {
    try {
      await opportunitiesApi.close(row.id)
      setNotice(`Closed “${row.title}”.`)
      await load()
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : 'Could not close the posting.')
    }
  }

  if (editing) {
    return (
      <>
        <PageHeader title={editing === 'new' ? 'New posting for a company' : 'Edit posting'} />
        <Card>
          <OpportunityForm
            isAdmin
            initial={editing === 'new' ? undefined : editing}
            onCancel={() => setEditing(null)}
            onSaved={(saved) => {
              setEditing(null)
              setNotice(`Saved “${saved.title}”.`)
              void load()
            }}
          />
        </Card>
      </>
    )
  }

  return (
    <>
      <PageHeader title="All postings" subtitle="Postings you create open straight away." />
      <div className="mb-4 flex justify-end">
        <Button onClick={() => setEditing('new')}>New posting</Button>
      </div>
      <div className="mb-4 grid gap-3 sm:grid-cols-4">
        <Select label="Status" value={status} onChange={(e) => setStatus(e.target.value as OpportunityStatus | '')}>
          <option value="">Any</option>
          {(Object.keys(OPPORTUNITY_STATUS_LABEL) as OpportunityStatus[]).map((s) => (
            <option key={s} value={s}>
              {OPPORTUNITY_STATUS_LABEL[s]}
            </option>
          ))}
        </Select>
        <Select label="Role type" value={roleType} onChange={(e) => setRoleType(e.target.value as RoleType | '')}>
          <option value="">Any</option>
          <option value="full_time">Full time</option>
          <option value="internship">Internship</option>
        </Select>
        <Field label="Company ID" value={companyId} onChange={(e) => setCompanyId(e.target.value)} />
        <Field label="Search" value={search} onChange={(e) => setSearch(e.target.value)} />
      </div>
      {error ? <div className="mb-4"><Alert tone="error">{error}</Alert></div> : null}
      {notice ? <div className="mb-4"><Alert tone="success">{notice}</Alert></div> : null}

      {rows === null && !error ? (
        <p className="py-8 text-center text-sm text-ink-400">Loading…</p>
      ) : rows && rows.length === 0 ? (
        <EmptyState title="No postings match" />
      ) : (
        <div className="overflow-x-auto rounded-xl border border-ink-200 bg-white">
          <table className="w-full text-sm">
            <caption className="sr-only">All postings</caption>
            <thead>
              <tr className="text-left text-xs text-ink-400">
                <th scope="col" className="p-3 font-medium">Title</th>
                <th scope="col" className="p-3 font-medium">Company</th>
                <th scope="col" className="p-3 font-medium">Status</th>
                <th scope="col" className="p-3 font-medium">Deadline</th>
                <th scope="col" className="p-3 font-medium">Actions</th>
              </tr>
            </thead>
            <tbody>
              {rows?.map((row) => (
                <tr key={row.id} className="border-t border-ink-100">
                  <td className="p-3 font-medium">{row.title}</td>
                  <td className="p-3">{row.company_name ?? row.company}</td>
                  <td className="p-3"><OpportunityStatusBadge status={row.status} /></td>
                  <td className="p-3">{row.deadline}</td>
                  <td className="flex flex-wrap gap-2 p-3">
                    {row.status !== 'closed' ? (
                      <Button size="sm" variant="secondary" onClick={() => setEditing(row)}>
                        Edit
                      </Button>
                    ) : null}
                    {row.status === 'open' ? (
                      <Button size="sm" variant="secondary" onClick={() => void close(row)}>
                        Close
                      </Button>
                    ) : null}
                    <Link
                      to={`/admin/opportunities/${row.id}/applicants`}
                      className="inline-flex items-center rounded-lg px-3 py-1.5 text-sm font-medium text-brand-700 ring-1 ring-ink-200 hover:bg-ink-50"
                    >
                      Applicants
                    </Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  )
}
