import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'

import { ApiError } from '@/api/client'
import {
  ROLE_LABELS,
  STATUS_LABELS,
  usersApi,
  type AccountRole,
  type AccountStatus,
  type DirectoryParams,
  type DirectorySummary,
  type DirectoryUser,
} from '@/api/users'
import { Alert, Badge, Button, Card, EmptyState, Field, PageHeader, Select } from '@/components/ui'

// Mirrors the backend's REST_FRAMEWORK PAGE_SIZE. Used only for the
// "Showing x–y" range; paging itself follows the server's `next`.
const PAGE_SIZE = 20

const ROLE_CARDS: Array<{ role: AccountRole; label: string }> = [
  { role: 'student', label: 'Students' },
  { role: 'admin', label: 'Placement admins' },
  { role: 'company', label: 'Recruiters' },
]

interface Filters {
  role: AccountRole | ''
  status: AccountStatus | ''
  school: string
  batch: string
  /** CMP-nnnn, set by clicking a recruiter's company. */
  company_id: string
}

const NO_FILTERS: Filters = { role: '', status: '', school: '', batch: '', company_id: '' }

type Company = NonNullable<DirectoryUser['company']>

function formatSignIn(value: string | null): string {
  if (!value) return 'Never'
  return new Date(value).toLocaleString(undefined, {
    day: 'numeric',
    month: 'short',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

/**
 * Every account on the portal, for the placement cell. Read-only.
 *
 * Each page load is recorded server-side as an identity read, so the list is
 * fetched on demand (filter change, search, page turn), never polled.
 */
export default function UsersPage() {
  const [users, setUsers] = useState<DirectoryUser[]>([])
  const [count, setCount] = useState(0)
  const [hasNext, setHasNext] = useState(false)
  const [summary, setSummary] = useState<DirectorySummary | null>(null)
  const [filters, setFilters] = useState<Filters>(NO_FILTERS)
  const [company, setCompany] = useState<Company | null>(null)
  const [search, setSearch] = useState('')
  const [appliedSearch, setAppliedSearch] = useState('')
  const [page, setPage] = useState(1)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  // Separate from the list so a failing summary does not blank the table.
  useEffect(() => {
    let cancelled = false
    usersApi
      .summary()
      .then((result) => !cancelled && setSummary(result))
      .catch(() => undefined)
    return () => {
      cancelled = true
    }
  }, [])

  useEffect(() => {
    // Filters can change faster than the server answers. Each run cancels the
    // one before it, so a slow answer to an older filter never lands under a
    // newer one.
    let cancelled = false
    const params: DirectoryParams = { ...filters, search: appliedSearch, page }
    setLoading(true)
    setError(null)
    usersApi
      .list(params)
      .then((result) => {
        if (cancelled) return
        setUsers(result.results)
        setCount(result.count)
        setHasNext(Boolean(result.next))
      })
      .catch((caught: unknown) => {
        if (cancelled) return
        // Rows from the previous request would read as the answer to this one.
        setUsers([])
        setCount(0)
        setHasNext(false)
        setError(caught instanceof ApiError ? caught.message : 'Could not load the users.')
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [filters, appliedSearch, page])

  function setFilter<K extends keyof Filters>(key: K, value: Filters[K]) {
    setFilters((current) => ({ ...current, [key]: value }))
    setPage(1)
  }

  const filtered =
    Object.values(filters).some(Boolean) || appliedSearch !== ''
  const firstRow = count === 0 ? 0 : (page - 1) * PAGE_SIZE + 1
  const lastRow = Math.min(page * PAGE_SIZE, count)

  return (
    <>
      <PageHeader
        title="All users"
        subtitle="Every account on the portal: students, placement admins and recruiters. Read-only, and every view is audited."
      />

      <div className="mb-6 grid gap-4 sm:grid-cols-4">
        <Card className="p-4">
          <p className="text-2xl font-semibold tabular-nums">{summary?.total ?? '—'}</p>
          <p className="text-sm text-ink-600">All accounts</p>
        </Card>
        {ROLE_CARDS.map((card) => (
          <button
            key={card.role}
            type="button"
            onClick={() => setFilter('role', filters.role === card.role ? '' : card.role)}
            aria-pressed={filters.role === card.role}
            className="text-left transition hover:opacity-80"
          >
            <Card
              className={`h-full p-4 ${filters.role === card.role ? 'border-brand-500 ring-1 ring-brand-500' : ''}`}
            >
              <p className="text-2xl font-semibold tabular-nums">
                {summary?.by_role[card.role] ?? '—'}
              </p>
              <p className="text-sm text-ink-600">{card.label}</p>
            </Card>
          </button>
        ))}
      </div>

      <Card className="mb-4 p-4">
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <Select
            label="Role"
            name="role"
            value={filters.role}
            onChange={(event) => setFilter('role', event.target.value as Filters['role'])}
          >
            <option value="">All roles</option>
            {(Object.keys(ROLE_LABELS) as AccountRole[]).map((role) => (
              <option key={role} value={role}>
                {ROLE_LABELS[role]}
              </option>
            ))}
          </Select>
          <Select
            label="Status"
            name="status"
            value={filters.status}
            onChange={(event) => setFilter('status', event.target.value as Filters['status'])}
          >
            <option value="">Any status</option>
            {(Object.keys(STATUS_LABELS) as AccountStatus[]).map((status) => (
              <option key={status} value={status}>
                {STATUS_LABELS[status]}
                {summary ? ` (${summary.by_status[status] ?? 0})` : ''}
              </option>
            ))}
          </Select>
          <Select
            label="School"
            name="school"
            value={filters.school}
            onChange={(event) => setFilter('school', event.target.value)}
          >
            <option value="">All schools</option>
            {(summary?.schools ?? []).map((school) => (
              <option key={school.key} value={school.key}>
                {school.name}
              </option>
            ))}
          </Select>
          <Select
            label="Batch"
            name="batch"
            value={filters.batch}
            onChange={(event) => setFilter('batch', event.target.value)}
          >
            <option value="">All batches</option>
            {(summary?.batches ?? []).map((batch) => (
              <option key={batch} value={String(batch)}>
                {batch}
              </option>
            ))}
          </Select>
        </div>

        <form
          className="mt-3 flex flex-wrap items-end gap-2"
          onSubmit={(event) => {
            event.preventDefault()
            setAppliedSearch(search.trim())
            setPage(1)
          }}
        >
          <div className="min-w-48 flex-1">
            <Field
              label="Search"
              name="search"
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder="Name, email, PRN, ADM- or CMP- id"
            />
          </div>
          <Button type="submit" variant="secondary">
            Search
          </Button>
          {filtered ? (
            <Button
              type="button"
              variant="ghost"
              onClick={() => {
                setFilters(NO_FILTERS)
                setCompany(null)
                setSearch('')
                setAppliedSearch('')
                setPage(1)
              }}
            >
              Clear filters
            </Button>
          ) : null}
        </form>
      </Card>

      {filters.company_id ? (
        <div className="mb-4">
          <Alert tone="info">
            Showing the recruiters at{' '}
            <span className="font-medium">{company?.name ?? filters.company_id}</span>{' '}
            <span className="font-mono text-xs">({filters.company_id})</span>.{' '}
            <button
              type="button"
              className="underline"
              onClick={() => {
                setCompany(null)
                setFilter('company_id', '')
              }}
            >
              Show everyone
            </button>
          </Alert>
        </div>
      ) : null}

      {error ? (
        <div className="mb-4">
          <Alert tone="error">{error}</Alert>
        </div>
      ) : null}

      {loading ? (
        <p className="py-8 text-center text-sm text-ink-400">Loading…</p>
      ) : error ? null : users.length === 0 ? (
        <EmptyState title={filtered ? 'No users match these filters' : 'No users yet'}>
          {filtered ? 'Try a different filter or clear the search.' : 'Accounts appear here as they are created.'}
        </EmptyState>
      ) : (
        <Card className="p-0">
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead className="border-b border-ink-200 text-xs tracking-wide text-ink-400 uppercase">
                <tr>
                  <th className="px-4 py-3 font-medium">Name</th>
                  <th className="py-3 pr-4 font-medium">Role</th>
                  <th className="py-3 pr-4 font-medium">Key</th>
                  <th className="py-3 pr-4 font-medium">Email</th>
                  <th className="py-3 pr-4 font-medium">Company / school</th>
                  <th className="py-3 pr-4 font-medium">Status</th>
                  <th className="py-3 pr-4 font-medium">Verified</th>
                  <th className="py-3 pr-4 font-medium">Onboarding</th>
                  <th className="py-3 pr-4 font-medium">Last sign-in</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-ink-100">
                {users.map((row) => (
                  <UserRow
                    key={row.id}
                    row={row}
                    onCompany={(picked) => {
                      setCompany(picked)
                      setFilters({ ...NO_FILTERS, company_id: picked.company_id })
                      setSearch('')
                      setAppliedSearch('')
                      setPage(1)
                    }}
                  />
                ))}
              </tbody>
            </table>
          </div>

          <div className="flex flex-wrap items-center justify-between gap-3 border-t border-ink-100 px-4 py-3">
            <p className="text-sm text-ink-600">
              Showing {firstRow}–{lastRow} of {count} account{count === 1 ? '' : 's'}
            </p>
            <div className="flex gap-2">
              <Button
                size="sm"
                variant="secondary"
                disabled={page === 1}
                onClick={() => setPage((current) => Math.max(1, current - 1))}
              >
                Previous
              </Button>
              <Button
                size="sm"
                variant="secondary"
                disabled={!hasNext}
                onClick={() => setPage((current) => current + 1)}
              >
                Next
              </Button>
            </div>
          </div>
        </Card>
      )}
    </>
  )
}

const ROLE_TONES = { student: 'neutral', admin: 'brand', company: 'warning' } as const

function UserRow({
  row,
  onCompany,
}: {
  row: DirectoryUser
  onCompany: (company: Company) => void
}) {
  const name = row.full_name || row.display_name || row.email
  const company = row.company
  return (
    <tr>
      <td className="px-4 py-2.5">
        {row.role === 'student' && row.student_id ? (
          <Link
            to={`/admin/profiles/${row.student_id}`}
            className="font-medium text-brand-700 hover:underline"
          >
            {name}
          </Link>
        ) : (
          <span className="font-medium text-ink-900">{name}</span>
        )}
      </td>
      <td className="py-2.5 pr-4">
        <Badge tone={ROLE_TONES[row.role]}>{ROLE_LABELS[row.role]}</Badge>
      </td>
      <td className="py-2.5 pr-4 font-mono text-xs">{row.human_key ?? '—'}</td>
      <td className="py-2.5 pr-4 text-ink-600">{row.email}</td>
      <td className="py-2.5 pr-4 text-ink-600">
        {company ? (
          <button
            type="button"
            onClick={() => onCompany(company)}
            className="text-left text-brand-700 hover:underline"
            title={`All recruiters at ${company.name}`}
          >
            {company.name}
          </button>
        ) : row.role === 'student' ? (
          <span>
            {row.school_name ?? '—'}
            {row.batch ? <span className="text-ink-400"> · {row.batch}</span> : null}
          </span>
        ) : (
          '—'
        )}
      </td>
      <td className="py-2.5 pr-4">
        <Badge tone={row.is_active ? 'success' : row.status === 'suspended' ? 'danger' : 'neutral'}>
          {STATUS_LABELS[row.status] ?? row.status_display}
        </Badge>
      </td>
      <td className="py-2.5 pr-4">
        {row.role !== 'student' ? (
          <span className="text-ink-400" title="Provisioned by the placement cell">
            n/a
          </span>
        ) : (
          <span className="flex flex-wrap gap-1">
            <Badge tone={row.is_verified ? 'success' : 'warning'}>
              {row.is_verified ? 'Email' : 'Email pending'}
            </Badge>
            {row.profile_verified ? <Badge tone="success">Profile</Badge> : null}
          </span>
        )}
      </td>
      <td className="py-2.5 pr-4 text-ink-600">
        {row.onboarding_completed === null ? (
          <span className="text-ink-400">n/a</span>
        ) : row.onboarding_completed ? (
          'Done'
        ) : (
          'Not yet'
        )}
      </td>
      <td className="py-2.5 pr-4 whitespace-nowrap text-ink-600">{formatSignIn(row.last_login)}</td>
    </tr>
  )
}
