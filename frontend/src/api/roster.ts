import { api, request, tokenStore } from '@/api/client'

export interface Paginated<T> {
  count: number
  next: string | null
  previous: string | null
  results: T[]
}

export interface RosterStudent {
  id: string
  prn: string
  email: string
  full_name: string
  department: string
  batch: number
  cgpa: string | null
  phone: string
  is_placement_eligible: boolean
  has_account: boolean
  created_at: string
}

export interface RowError {
  row: number
  prn: string
  errors: Record<string, string[]>
}

export interface UploadResult {
  dry_run: boolean
  created: number
  updated: number
  unchanged: number
  processed: number
  error_count: number
  errors: RowError[]
}

export type FlagStatus = 'open' | 'resolved' | 'dismissed'

export interface FlaggedSignup {
  id: string
  prn: string
  email: string
  reason: string
  reason_display: string
  attempts: number
  status: FlagStatus
  admin_note: string
  reviewed_by_email: string | null
  reviewed_at: string | null
  created_at: string
  updated_at: string
}

function query(params: Record<string, string | number | undefined>): string {
  const search = new URLSearchParams()
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== '') search.set(key, String(value))
  }
  const asString = search.toString()
  return asString ? `?${asString}` : ''
}

export const rosterApi = {
  /**
   * Multipart upload. A partially-valid file answers 207, which `request`
   * treats as success, so the caller gets the per-row errors rather than
   * an exception.
   */
  upload: (file: File, dryRun: boolean) => {
    const form = new FormData()
    form.append('file', file)
    form.append('dry_run', String(dryRun))
    return request<UploadResult>('/api/roster/upload', { method: 'POST', body: form })
  },

  students: (params: { search?: string; department?: string; batch?: number; page?: number } = {}) =>
    api.get<Paginated<RosterStudent>>(`/api/roster/students${query(params)}`),

  flagged: (params: { status?: FlagStatus; search?: string; page?: number } = {}) =>
    api.get<Paginated<FlaggedSignup>>(`/api/roster/flagged${query(params)}`),

  review: (id: string, status: 'resolved' | 'dismissed', adminNote: string) =>
    api.post<FlaggedSignup>(`/api/roster/flagged/${id}/review`, {
      status,
      admin_note: adminNote,
    }),
}

export { tokenStore }
