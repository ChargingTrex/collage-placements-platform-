import { api } from '@/api/client'
import type { MatchComponent, MatchComponentName } from '@/api/matching'
import type { Paginated } from '@/api/roster'

export type OpportunityStatus = 'draft' | 'pending_review' | 'open' | 'closed' | 'rejected'
export type RoleType = 'internship' | 'full_time'
export type EducationLevelCode = 'UG' | 'Masters' | 'PG'
export type ApplicationStatus =
  | 'applied'
  | 'shortlisted'
  | 'interview'
  | 'offer'
  | 'rejected'
  | 'withdrawn'

export const OPPORTUNITY_STATUS_LABEL: Record<OpportunityStatus, string> = {
  draft: 'Draft',
  pending_review: 'Pending review',
  open: 'Open',
  closed: 'Closed',
  rejected: 'Rejected',
}

export const APPLICATION_STATUS_LABEL: Record<ApplicationStatus, string> = {
  applied: 'Applied',
  shortlisted: 'Shortlisted',
  interview: 'Interview',
  offer: 'Offer',
  rejected: 'Rejected',
  withdrawn: 'Withdrawn',
}

/** What an owner company or admin may move an application to. Mirrors the server. */
export const ALLOWED_TRANSITIONS: Record<ApplicationStatus, ApplicationStatus[]> = {
  applied: ['shortlisted', 'rejected'],
  shortlisted: ['interview', 'rejected'],
  interview: ['offer', 'rejected'],
  offer: [],
  rejected: [],
  withdrawn: [],
}

/** Statuses a student may withdraw from. */
export const WITHDRAWABLE: ApplicationStatus[] = ['applied', 'shortlisted', 'interview']

export interface Opportunity {
  id: string
  /** Company UUID. */
  company: string
  company_name?: string
  title: string
  description: string
  role_type: RoleType
  location: string
  openings: number
  required_skills: string[]
  eligible_departments: string[]
  min_cgpa: string | number | null
  min_experience_years: string | number | null
  required_education_levels: EducationLevelCode[]
  salary_disclosed: boolean
  salary_min: number | null
  salary_max: number | null
  salary_period: 'month' | 'year'
  salary_currency: string
  deadline: string
  similarity_threshold: number | null
  status: OpportunityStatus
  submitted_at?: string | null
  approved_at?: string | null
  rejection_reason?: string
  created_at?: string
}

/** Body of create and edit. An admin also sends `company`. */
export interface OpportunityInput {
  company?: string
  title: string
  description: string
  role_type: RoleType
  location: string
  openings: number
  required_skills: string[]
  eligible_departments: string[]
  min_cgpa: number | null
  min_experience_years: number | null
  required_education_levels: EducationLevelCode[]
  salary_disclosed: boolean
  salary_min: number | null
  salary_max: number | null
  salary_period: 'month' | 'year'
  deadline: string
  similarity_threshold: number | null
}

export interface FeedRow extends Opportunity {
  score: number
  components: Record<MatchComponentName, MatchComponent>
  matched_skills: string[]
  missing_skills: string[]
  eligible: boolean
  eligibility_reasons: string[]
  has_applied: boolean
  application_status: ApplicationStatus | null
}

export interface ApplicationEvent {
  from_status: ApplicationStatus | ''
  to_status: ApplicationStatus
  note: string
  created_at: string
}

/** The company's view: an allow-list. Nothing outside these keys is rendered. */
export interface CompanyApplication {
  id: string
  status: ApplicationStatus
  applied_at: string
  score: number
  similarity: number
  eligible: boolean
  eligibility_reasons: string[]
  opportunity: { id: string; title: string }
  prn: string
  full_name: string
  department: string
  programme: string
  school: string
  batch: number
  year_of_study: number | string | null
  cgpa_at_apply: string | number | null
  skills: string[]
  resume_url: string | null
  contact: { email: string; phone: string } | null
  contact_available: boolean
}

/** The student's own view adds the event timeline. */
export interface StudentApplication extends CompanyApplication {
  events: ApplicationEvent[]
}

export interface ScreenRow {
  application_id: string
  prn: string
  full_name: string
  score: number
  experience_years: number | null
  education_levels: string[]
  reasons: string[]
}

export interface ScreenResult {
  shortlisted: ScreenRow[]
  below_threshold: ScreenRow[]
  filtered_out: ScreenRow[]
}

export interface ScreenInput {
  threshold?: number
  min_experience_years?: number
  required_education_levels?: EducationLevelCode[]
}

export interface OpportunityStats {
  opportunities_by_status: Record<string, number>
  applications_by_status: Record<string, number>
  per_opportunity: Array<{
    id: string
    title: string
    company: string
    applicants: number
    by_status: Record<string, number>
  }>
  median_hours_to_shortlist: number | null
}

export interface OpportunityFilters {
  status?: OpportunityStatus | ''
  role_type?: RoleType | ''
  company_id?: string
  search?: string
}

type QueryParams = Record<string, string | number | undefined>

function query(params: QueryParams): string {
  const search = new URLSearchParams()
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== '') search.set(key, String(value))
  }
  const asString = search.toString()
  return asString ? `?${asString}` : ''
}

/** The contract does not say whether lists are paginated; accept both. */
export function rowsOf<T>(body: Paginated<T> | T[]): T[] {
  return Array.isArray(body) ? body : body.results
}

const BASE = '/api/opportunities'

export const opportunitiesApi = {
  list: async (filters: OpportunityFilters = {}) =>
    rowsOf(
      await api.get<Paginated<Opportunity> | Opportunity[]>(`${BASE}/${query({ ...filters })}`),
    ),
  create: (input: OpportunityInput) => api.post<Opportunity>(`${BASE}/`, input),
  update: (id: string, input: Partial<OpportunityInput>) =>
    api.patch<Opportunity>(`${BASE}/${id}`, input),
  remove: (id: string) => api.delete<void>(`${BASE}/${id}`),
  submit: (id: string) => api.post<Opportunity>(`${BASE}/${id}/submit`),
  approve: (id: string) => api.post<Opportunity>(`${BASE}/${id}/approve`),
  reject: (id: string, reason: string) => api.post<Opportunity>(`${BASE}/${id}/reject`, { reason }),
  close: (id: string) => api.post<Opportunity>(`${BASE}/${id}/close`),
  feed: async () => rowsOf(await api.get<Paginated<FeedRow> | FeedRow[]>(`${BASE}/feed`)),
  apply: (id: string) => api.post<StudentApplication>(`${BASE}/${id}/apply`),
  screen: (id: string, input: ScreenInput) =>
    api.post<ScreenResult>(`${BASE}/${id}/screen`, input),
  applicantsExportUrl: (id: string) => `${BASE}/${id}/applicants/export`,
  stats: () => api.get<OpportunityStats>(`${BASE}/stats`),

  applications: async (params: { opportunity?: string; status?: ApplicationStatus | '' } = {}) =>
    rowsOf(
      await api.get<Paginated<CompanyApplication> | CompanyApplication[]>(
        `${BASE}/applications${query(params)}`,
      ),
    ),
  myApplications: async () =>
    rowsOf(
      await api.get<Paginated<StudentApplication> | StudentApplication[]>(`${BASE}/applications`),
    ),
  withdraw: (id: string) => api.post<StudentApplication>(`${BASE}/applications/${id}/withdraw`),
  setStatus: (id: string, status: ApplicationStatus, note?: string) =>
    api.post<CompanyApplication>(`${BASE}/applications/${id}/status`, {
      status,
      ...(note ? { note } : {}),
    }),
}

/** Why apply can be refused (D28): one plain sentence per server `reason`. */
export const APPLY_REFUSALS: Record<string, string> = {
  not_open: 'This posting is not open for applications.',
  deadline_passed: 'The deadline for this posting has passed.',
  already_applied: 'You have already applied to this posting.',
  no_resume: 'Upload a resume to your profile before applying.',
  not_eligible:
    'You do not meet this posting’s department or CGPA requirement, so you cannot apply.',
}

export function describeApplyRefusal(reason: string, fallback: string): string {
  return APPLY_REFUSALS[reason] ?? fallback
}

export function formatSalary(
  o: Pick<
    Opportunity,
    'salary_disclosed' | 'salary_min' | 'salary_max' | 'salary_period' | 'salary_currency'
  >,
): string {
  if (!o.salary_disclosed || (o.salary_min === null && o.salary_max === null)) {
    return 'Salary not disclosed'
  }
  const fmt = (n: number) => n.toLocaleString('en-IN')
  const range =
    o.salary_min !== null && o.salary_max !== null && o.salary_min !== o.salary_max
      ? `${fmt(o.salary_min)} – ${fmt(o.salary_max)}`
      : fmt((o.salary_min ?? o.salary_max) as number)
  return `${o.salary_currency || 'INR'} ${range} per ${o.salary_period}`
}
