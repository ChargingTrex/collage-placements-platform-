import { api, request } from '@/api/client'
import type { JobSummary, MatchScore } from '@/api/matching'
import type { Paginated } from '@/api/roster'

export type Visibility = 'all' | 'shortlisted' | 'hidden'
export type EducationLevel = 'UG' | 'Masters' | 'PG' | ''

export interface RosterFacts {
  prn: string
  full_name: string
  email: string
  department: string
  batch: number
  cgpa: string | null
  /** Present on own and admin payloads. */
  school?: string
  year_of_study?: number | string | null
}

/** Roster facts as the onboarding payload carries them. */
export interface OnboardingStudent {
  prn: string
  full_name: string
  email: string
  department: string
  school: string
  batch: number
  year_of_study: number | string | null
}

export type CareerPath =
  | 'placement'
  | 'business'
  | 'higher_studies'
  | 'entrepreneurship'
  | 'research'
  | 'family_business'
  | 'competitive_exams'
  | 'other'
  | 'undecided'

/**
 * The explanation sits beside every option because Business,
 * Entrepreneurship and Family business read alike and students mix them up.
 */
export const CAREER_PATHS: ReadonlyArray<{ value: CareerPath; label: string; explain: string }> = [
  {
    value: 'placement',
    label: 'Placement / campus recruitment',
    explain: 'Taking a job through the campus placement process.',
  },
  {
    value: 'business',
    label: 'Business',
    explain: "Joining an existing business that is not your family's.",
  },
  {
    value: 'higher_studies',
    label: 'Higher studies',
    explain: "A master's or other degree, in India or abroad.",
  },
  {
    value: 'entrepreneurship',
    label: 'Entrepreneurship',
    explain: 'Founding a new venture of your own.',
  },
  {
    value: 'research',
    label: 'Research',
    explain: 'A research role or a research-led programme.',
  },
  {
    value: 'family_business',
    label: 'Taking over family business',
    explain: "Joining or succeeding in your family's business.",
  },
  {
    value: 'competitive_exams',
    label: 'Preparation for competitive exams / UPSC',
    explain: 'Preparing full time for UPSC or another competitive exam.',
  },
  { value: 'other', label: 'Other', explain: 'Something not listed here. Tell us what.' },
  { value: 'undecided', label: 'Not decided yet', explain: 'You have not settled on a path.' },
]

export function careerPathLabel(value: string): string {
  return CAREER_PATHS.find((path) => path.value === value)?.label ?? value
}

export type CgpaReviewStatus = 'not_needed' | 'open' | 'resolved'

/** The two school levels a student records, as they appear in the URL. */
export type MarksheetLevel = '10' | '12'
export const MARKSHEET_LEVELS: ReadonlyArray<{ level: MarksheetLevel; label: string }> = [
  { level: '10', label: 'Class 10' },
  { level: '12', label: 'Class 12' },
]

export type Board = 'cbse' | 'icse' | 'state' | 'ib' | 'cambridge' | 'other'
export const BOARDS: ReadonlyArray<{ value: Board; label: string }> = [
  { value: 'cbse', label: 'CBSE' },
  { value: 'icse', label: 'ICSE / CISCE' },
  { value: 'state', label: 'State board' },
  { value: 'ib', label: 'International Baccalaureate' },
  { value: 'cambridge', label: 'Cambridge / IGCSE' },
  { value: 'other', label: 'Other' },
]

export function boardLabel(value: string): string {
  return BOARDS.find((board) => board.value === value)?.label ?? value
}

/** Every CGPA on record for a profile, and which pairs disagree. Admin only. */
export interface CgpaSources {
  values: Record<string, number | null>
  labels: Record<string, string>
  tolerance: number
  disagreements: Array<{
    sources: string[]
    values: Record<string, number>
    message: string
  }>
}

export interface Skill {
  id: string
  name: string
  slug: string
  category: 'technical' | 'tool' | 'soft'
}

export type ExperienceKind = 'internship' | 'part_time' | 'full_time' | 'volunteer' | 'freelance'

export interface ExperienceEntry {
  id: string
  role: string
  organization: string
  kind: ExperienceKind
  start_date: string
  end_date: string | null
  location: string
  description: string
  skills_used: string[]
  is_current: boolean
  duration_months: number
}

export interface ProjectEntry {
  id: string
  title: string
  description: string
  tech_stack: string[]
  role: string
  team_size: number | null
  repo_url: string
  demo_url: string
  video_url: string
  started_on: string | null
  completed_on: string | null
}

export interface OwnProfile {
  id: string
  /** What a client addresses this profile by. PRN is display and reconciliation only. */
  student_id: string
  student: RosterFacts
  headline: string
  summary: string
  phone: string
  github_url: string
  linkedin_url: string
  website_url: string
  experience_years: string
  education_level: EducationLevel
  visibility: Visibility
  /** How many companies would still see this profile under 'shortlisted'. */
  shortlisted_by_count: number
  is_verified: boolean
  verified_at: string | null
  verified_by_email: string | null
  skills: Skill[]
  experience_entries: ExperienceEntry[]
  projects: ProjectEntry[]
  completion_percent: number
  completion_detail: Record<string, boolean>
  /** An API url that needs the bearer token: open it with `openDocument`, never as a link. */
  resume_url: string | null
  resume_filename: string
  resume_uploaded_at: string | null
  /** Placement-cell planning only. The company payload never carries it. */
  career_path: CareerPath
  career_path_detail: string
  also_attending_placements: boolean
  personal_email: string
  onboarding_completed: boolean
  onboarding_completed_at: string | null
  transcript_url: string | null
  transcript_filename: string
  transcript_prn: string
  transcript_school: string
  transcript_degree: string
  /** The printed `Cumulative GPA`. */
  parsed_cgpa: string | null
  /** Sum of credits x SGPA over the sum of credits. */
  recomputed_cgpa: string | null
  confirmed_cgpa: string | null
  /** Null until a transcript is read. */
  cgpa_matches_roster: boolean | null
  cgpa_review_status: CgpaReviewStatus
  /** School marksheets. The file and the marks are stated separately. */
  marksheet_10_url: string | null
  marksheet_10_filename: string
  marksheet_10_uploaded_at: string | null
  marks_10_percentage: string | null
  marks_10_board: Board | ''
  marks_10_year: number | null
  marksheet_12_url: string | null
  marksheet_12_filename: string
  marksheet_12_uploaded_at: string | null
  marks_12_percentage: string | null
  marks_12_board: Board | ''
  marks_12_year: number | null
  parsed_experience_years: string | null
  parsed_education_levels: string[]
  parsed_values_confirmed: boolean
  parsed_differs_from_confirmed: boolean
  /**
   * The role categories the profile was sorted into. Only the student's own
   * `me` payload carries it; empty until recruiters' JDs define categories.
   */
  categories?: string[]
  updated_at: string
}

export interface CompanyProfile {
  id: string
  /** What a client addresses this profile by. PRN is display and reconciliation only. */
  student_id: string
  prn: string
  student: RosterFacts
  headline: string
  summary: string
  experience_years: string
  education_level: EducationLevel
  is_verified: boolean
  verified_at: string | null
  skills: Skill[]
  experience_entries: ExperienceEntry[]
  projects: ProjectEntry[]
  completion_percent: number
  contact: { email: string; phone: string } | null
  resume_url: string | null
  is_shortlisted: boolean
  updated_at: string
}

export interface ResumeSuggestion {
  experience_years: number
  education_level: EducationLevel | null
  /** False when the student had already confirmed their own values. */
  applied: boolean
}

export type AnalysisStatus = 'pending' | 'done' | 'failed' | 'skipped'
export type AnalysisSource = 'llm' | 'regex'
export type ReadLevel = Exclude<EducationLevel, ''>

/** What each reader made of one field, and whether they agree. */
export interface Agreement<T> {
  regex: T | null
  llm: T | null
  agree: boolean
}

/** A resume role with no form entry, shaped for `POST me/experience`. */
export interface SuggestedExperience {
  role: string
  organization: string
  start_date: string | null
  end_date: string | null
  description: string
  /** Absent when the resume did not say; the student picks one. */
  kind?: ExperienceKind
}

/**
 * The student's view of the full resume reading. An allow-list on the
 * server: no age, DOB, resume CGPA or contact details ever arrive here.
 */
export interface ResumeAnalysis {
  status: AnalysisStatus
  source: AnalysisSource | null
  model_name: string | null
  analysed_at: string | null
  experience_years: number | null
  education_level: ReadLevel | null
  agreement: {
    experience_years?: Agreement<number>
    education_level?: Agreement<ReadLevel>
  }
  categories: string[]
  /** The reading fell back to regex; asking again may get the model's. */
  retryable: boolean
  suggested_skills: string[]
  suggested_experience: SuggestedExperience[]
}

const ANALYSIS_STATUSES: readonly string[] = ['pending', 'done', 'failed', 'skipped']

/** True for a well-formed reading; anything else is treated as no reading. */
export function isResumeAnalysis(value: unknown): value is ResumeAnalysis {
  if (typeof value !== 'object' || value === null || !('status' in value)) return false
  return typeof value.status === 'string' && ANALYSIS_STATUSES.includes(value.status)
}

export interface OwnMatch {
  match: MatchScore
  job: JobSummary
}

export type JsonValue = string | number | boolean | null | JsonValue[] | { [key: string]: JsonValue }

/** One preliminary-verification flag. Advice for an admin, never a verdict. */
export interface VerificationFlag {
  field: string
  severity: 'info' | 'warning'
  sources: string[]
  /** Source name -> what that source says. */
  values: Record<string, JsonValue>
  message: string
}

/** What the resume says about age, DOB, CGPA and contacts. Admin-only. */
export interface ResumeFactsAdmin {
  age: number | null
  date_of_birth: string | null
  cgpa: number | null
  phones: string[]
  emails: string[]
  source: AnalysisSource | null
}

export interface AdminProfile extends OwnProfile {
  verification_checks: VerificationFlag[]
  warning_count: number
}

export interface AdminProfileDetail extends AdminProfile {
  resume_facts_admin: ResumeFactsAdmin | null
  cgpa_sources: CgpaSources
}

export interface Onboarding {
  completed: boolean
  dismissed: boolean
  student: OnboardingStudent
  phone: string
  personal_email: string
  career_path: CareerPath
  career_path_detail: string
  also_attending_placements: boolean
  headline: string
  summary: string
}

export type OnboardingSubmission = Omit<Onboarding, 'completed' | 'dismissed' | 'student'>

export interface Outcomes {
  batch: number | null
  paths: Array<{ value: string; label: string }>
  rows: Array<{
    school: string
    school_name: string
    counts: Record<string, number>
    total: number
  }>
  totals: Record<string, number>
  grand_total: number
  also_attending_placements: number
  verified: number
}

export interface ProfileStats {
  profiles: number
  onboarding_completed?: number
  verified: number
  with_resume: number
  fully_complete: number
  average_completion_percent: number
  visibility: Record<string, number>
}

export interface StudentSearchParams extends QueryParams {
  search?: string
  department?: string
  skills?: string
  project_keyword?: string
  cgpa_min?: string
  cgpa_max?: string
  min_experience_years?: string
  education_level?: string
  verified?: string
  /** A role category name, any case. */
  category?: string
  /** Graduating year. */
  batch?: string
  page?: number
}

/**
 * The admin list's extra filters, kept off `StudentSearchParams` for the same
 * reason the backend keeps them off the shared filter set: `career_path` is
 * placement-cell planning data, and the company list rejects it.
 */
export interface AdminSearchParams extends StudentSearchParams {
  career_path?: CareerPath
  /** A school key, e.g. `computing_data_science`. */
  school?: string
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

/** New entries arrive without an id; the API assigns one. */
export type NewExperience = Omit<ExperienceEntry, 'id' | 'is_current' | 'duration_months'>
export type NewProject = Omit<ProjectEntry, 'id'>

export const profilesApi = {
  me: () => api.get<OwnProfile>('/api/profiles/me'),
  updateMe: (changes: Partial<OwnProfile>) => api.patch<OwnProfile>('/api/profiles/me', changes),

  setVisibility: (visibility: Visibility) =>
    request<{ visibility: Visibility }>('/api/profiles/me/visibility', {
      method: 'PUT',
      body: { visibility },
    }),

  uploadResume: (file: File) => {
    const form = new FormData()
    form.append('file', file)
    return request<{ suggestion: ResumeSuggestion; analysis: ResumeAnalysis; profile: OwnProfile }>(
      '/api/profiles/me/resume',
      { method: 'POST', body: form },
    )
  },
  deleteResume: () => api.delete<void>('/api/profiles/me/resume'),
  /** Synchronous, within a server time budget; idempotent on the resume text. */
  analyzeResume: () => api.post<ResumeAnalysis>('/api/profiles/me/resume/analyze'),
  resumeAnalysis: () => api.get<ResumeAnalysis>('/api/profiles/me/resume/analysis'),
  myMatch: (jdText: string) => api.post<OwnMatch>('/api/profiles/me/match', { jd_text: jdText }),

  confirmParsed: (experienceYears: string, educationLevel: EducationLevel) =>
    api.post<OwnProfile>('/api/profiles/me/confirm-parsed', {
      experience_years: experienceYears,
      education_level: educationLevel,
    }),

  addExperience: (entry: Partial<NewExperience>) =>
    api.post<ExperienceEntry>('/api/profiles/me/experience', entry),
  updateExperience: (id: string, entry: Partial<NewExperience>) =>
    api.patch<ExperienceEntry>(`/api/profiles/me/experience/${id}`, entry),
  deleteExperience: (id: string) => api.delete<void>(`/api/profiles/me/experience/${id}`),

  addProject: (entry: Partial<NewProject>) =>
    api.post<ProjectEntry>('/api/profiles/me/projects', entry),
  updateProject: (id: string, entry: Partial<NewProject>) =>
    api.patch<ProjectEntry>(`/api/profiles/me/projects/${id}`, entry),
  deleteProject: (id: string) => api.delete<void>(`/api/profiles/me/projects/${id}`),

  addSkill: (name: string, category: Skill['category']) =>
    api.post<Skill>('/api/profiles/me/skills', { name, category }),
  deleteSkill: (id: string) => api.delete<void>(`/api/profiles/me/skills/${id}`),

  searchStudents: (params: StudentSearchParams = {}) =>
    api.get<Paginated<CompanyProfile>>(`/api/profiles/students${query(params)}`),
  student: (studentId: string) => api.get<CompanyProfile>(`/api/profiles/students/${studentId}`),
  shortlist: (studentId: string, note = '') =>
    api.post<{ shortlisted: boolean }>(`/api/profiles/students/${studentId}/shortlist`, { note }),
  unshortlist: (studentId: string) =>
    api.delete<void>(`/api/profiles/students/${studentId}/shortlist`),

  adminList: (params: AdminSearchParams = {}) =>
    api.get<Paginated<AdminProfile>>(`/api/profiles/admin${query(params)}`),
  adminProfile: (studentId: string) =>
    api.get<AdminProfileDetail>(`/api/profiles/admin/${studentId}`),
  adminStats: () => api.get<ProfileStats>('/api/profiles/admin/stats'),
  adminCgpaReview: (studentId: string, note = '') =>
    api.post<AdminProfileDetail>(`/api/profiles/admin/${studentId}/cgpa-review`, {
      status: 'resolved',
      note,
    }),
  outcomes: (batch?: string) =>
    api.get<Outcomes>(`/api/profiles/admin/outcomes${query({ batch })}`),
  outcomesExportUrl: (batch?: string) => `/api/profiles/admin/outcomes/export${query({ batch })}`,

  uploadTranscript: (file: File) => {
    const form = new FormData()
    form.append('file', file)
    return request<OwnProfile>('/api/profiles/me/transcript', { method: 'POST', body: form })
  },
  confirmCgpa: (cgpa: string) => api.post<OwnProfile>('/api/profiles/me/confirm-cgpa', { cgpa }),

  uploadMarksheet: (level: MarksheetLevel, file: File) => {
    const body = new FormData()
    body.append('file', file)
    return api.post<OwnProfile>(`/api/profiles/me/marksheet/${level}`, body)
  },
  deleteMarksheet: (level: MarksheetLevel) =>
    api.delete<OwnProfile>(`/api/profiles/me/marksheet/${level}`),

  onboarding: () => api.get<Onboarding>('/api/profiles/me/onboarding'),
  submitOnboarding: (submission: OnboardingSubmission) =>
    api.post<Onboarding>('/api/profiles/me/onboarding', submission),
  dismissOnboarding: () => api.post<void>('/api/profiles/me/onboarding/dismiss'),

  setVerification: (studentId: string, isVerified: boolean, note = '') =>
    api.post<AdminProfileDetail>(`/api/profiles/admin/${studentId}/verification`, {
      is_verified: isVerified,
      note,
    }),
}
