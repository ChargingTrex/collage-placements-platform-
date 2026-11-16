import { api } from '@/api/client'
import type { Paginated } from '@/api/roster'

/** The `role` column as the backend stores it, not the token's role names. */
export type AccountRole = 'student' | 'admin' | 'company'

export type AccountStatus =
  | 'provisional'
  | 'active'
  | 'on_leave'
  | 'graduated'
  | 'withdrawn'
  | 'suspended'

export interface DirectoryUser {
  id: string
  full_name: string
  display_name: string
  email: string
  role: AccountRole
  /** PRN for a student, ADM-nnnn for an admin, the company's CMP-nnnn for a recruiter. */
  human_key: string | null
  prn: string | null
  admin_id: string | null
  company: { id: string; company_id: string; name: string } | null
  status: AccountStatus
  status_display: string
  /** Can sign in right now: verified and in a status that permits it. */
  is_active: boolean
  /** Students only (email proved at signup); null for staff-provisioned logins. */
  is_verified: boolean | null
  profile_verified: boolean | null
  onboarding_completed: boolean | null
  /** Set only when the student has a profile, so the admin detail page exists. */
  student_id: string | null
  school: string | null
  school_name: string | null
  batch: number | null
  last_login: string | null
  date_joined: string
}

export interface DirectoryPage extends Paginated<DirectoryUser> {
  /** Present when `prns` was sent. */
  unmatched_prns?: string[]
}

export interface DirectorySummary {
  total: number
  by_role: Record<AccountRole, number>
  by_status: Record<AccountStatus, number>
  schools: Array<{ key: string; name: string }>
  batches: number[]
}

export interface DirectoryParams {
  role?: AccountRole | ''
  status?: AccountStatus | ''
  school?: string
  batch?: string | number
  search?: string
  company_id?: string
  page?: number
}

function query(params: object): string {
  const search = new URLSearchParams()
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== null && value !== '') search.set(key, String(value))
  }
  const asString = search.toString()
  return asString ? `?${asString}` : ''
}

export const usersApi = {
  /** Every account. Each call is written to the audit log as an identity read. */
  list: (params: DirectoryParams = {}) =>
    api.get<DirectoryPage>(`/api/auth/admin/users${query(params)}`),

  summary: () => api.get<DirectorySummary>('/api/auth/admin/users/summary'),
}

export const ROLE_LABELS: Record<AccountRole, string> = {
  student: 'Student',
  admin: 'Placement admin',
  company: 'Recruiter',
}

export const STATUS_LABELS: Record<AccountStatus, string> = {
  provisional: 'Provisional',
  active: 'Active',
  on_leave: 'On leave',
  graduated: 'Graduated',
  withdrawn: 'Withdrawn',
  suspended: 'Suspended',
}
