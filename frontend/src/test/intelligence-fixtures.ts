import type { MatchResult, MatchScore } from '@/api/matching'
import type {
  AdminProfile,
  AdminProfileDetail,
  CgpaSources,
  ResumeAnalysis,
  ResumeFactsAdmin,
  VerificationFlag,
} from '@/api/profiles'
import { makeCompanyProfile, makeOwnProfile } from '@/test/fixtures'
import type { Route } from '@/test/harness'

/** A finished model reading, with one suggestion of each kind. */
export function makeAnalysis(overrides: Partial<ResumeAnalysis> = {}): ResumeAnalysis {
  return {
    status: 'done',
    source: 'llm',
    model_name: 'llama3.1:8b',
    analysed_at: '2026-10-19T10:00:00Z',
    experience_years: 1.5,
    education_level: 'UG',
    agreement: {
      experience_years: { regex: 1, llm: 1.5, agree: true },
      education_level: { regex: 'UG', llm: 'UG', agree: true },
    },
    categories: ['Backend Engineer'],
    retryable: false,
    suggested_skills: ['Docker', 'PostgreSQL'],
    suggested_experience: [
      {
        role: 'Software Intern',
        organization: 'Loadstar Logistics',
        start_date: '2023-06-01',
        end_date: '2023-08-31',
        description: 'Built shipment-tracking APIs.',
        kind: 'internship',
      },
    ],
    ...overrides,
  }
}

/** The regex fallback: no comparison, and a retry may get the model's reading. */
export function makeRegexAnalysis(overrides: Partial<ResumeAnalysis> = {}): ResumeAnalysis {
  return makeAnalysis({
    source: 'regex',
    model_name: null,
    experience_years: 1,
    agreement: {},
    retryable: true,
    suggested_skills: [],
    suggested_experience: [],
    ...overrides,
  })
}

export const PENDING_ANALYSIS = makeAnalysis({
  status: 'pending',
  source: null,
  model_name: null,
  analysed_at: null,
  experience_years: null,
  education_level: null,
  agreement: {},
  categories: [],
  suggested_skills: [],
  suggested_experience: [],
})

export function makeMatchScore(overrides: Partial<MatchScore> = {}): MatchScore {
  return {
    score: 72,
    components: {
      // TF-IDF's raw cosine, calibrated on its 0-0.25 range (MATCH_SCORE): 0.2 reads as 0.8.
      semantic: { score: 0.8, weight: 0.45, raw: 0.2 },
      skills: { score: 0.5, weight: 0.35 },
      experience: { score: 1, weight: 0.1 },
      education: { score: 1, weight: 0.1 },
    },
    matched_skills: ['Python', 'Django'],
    missing_skills: ['Docker'],
    hard_filter_failures: [],
    flagged: false,
    semantic_source: 'tfidf',
    ...overrides,
  }
}

export const JOB_SUMMARY = {
  canonical_role: 'Backend Engineer',
  required_skills: ['Python', 'Django', 'Docker'],
  min_experience_years: 1,
  education_levels: [],
  source: 'llm' as const,
}

export function makeMatchResult(
  overrides: Partial<MatchResult> = {},
  match: Partial<MatchScore> = {},
): MatchResult {
  return {
    ...makeCompanyProfile(),
    categories: ['Backend Engineer'],
    match: makeMatchScore(match),
    ...overrides,
  }
}

export const CGPA_FLAG: VerificationFlag = {
  field: 'cgpa',
  severity: 'warning',
  sources: ['roster', 'resume'],
  values: { roster: 8.72, resume: 9.4 },
  message: 'The roster CGPA (8.72) and the resume CGPA (9.4) differ by more than 0.1.',
}

export const EMAIL_FLAG: VerificationFlag = {
  field: 'email',
  severity: 'info',
  sources: ['roster', 'resume'],
  values: { roster: 'aarav.mehta@college.edu', resume: ['aarav.m@gmail.example'] },
  message: 'The college email is not on the resume.',
}

/** Admin-only facts. Their values must never render on a student or company page. */
/** Every CGPA on record, all agreeing. Override `disagreements` to flag one. */
export const CGPA_SOURCES: CgpaSources = {
  values: {
    roster: 8.72,
    transcript_printed: 8.72,
    transcript_recomputed: 8.72,
    student: null,
  },
  labels: {
    roster: 'Roster',
    transcript_printed: 'Printed on transcript',
    transcript_recomputed: 'Recomputed from semesters',
    student: 'Stated by the student',
  },
  tolerance: 0.1,
  disagreements: [],
}

export const RESUME_FACTS: ResumeFactsAdmin = {
  age: 22,
  date_of_birth: '2003-05-14',
  cgpa: 9.4,
  phones: ['9820011001'],
  emails: ['aarav.m@gmail.example'],
  source: 'llm',
}

export function makeAdminProfile(overrides: Partial<AdminProfile> = {}): AdminProfile {
  return {
    ...makeOwnProfile({ resume_filename: 'aarav_mehta_backend.pdf' }),
    verification_checks: [],
    warning_count: 0,
    ...overrides,
  }
}

export function makeAdminDetail(overrides: Partial<AdminProfileDetail> = {}): AdminProfileDetail {
  return {
    ...makeAdminProfile({ verification_checks: [CGPA_FLAG, EMAIL_FLAG], warning_count: 1 }),
    resume_facts_admin: RESUME_FACTS,
    cgpa_sources: CGPA_SOURCES,
    ...overrides,
  }
}

/**
 * The fields a leaky server might add to a student or company payload. The
 * UI renders by allow-list, so none of these values may appear.
 */
export const LEAKED_FIELDS = {
  age: RESUME_FACTS.age,
  date_of_birth: RESUME_FACTS.date_of_birth,
  resume_cgpa: RESUME_FACTS.cgpa,
  cgpa_resume: RESUME_FACTS.cgpa,
  resume_facts_admin: RESUME_FACTS,
  verification_checks: [CGPA_FLAG],
  warning_count: 1,
}

/** A route that answers with each body in turn, repeating the last. */
export function sequenced(route: Omit<Route, 'body'>, bodies: unknown[]): Route {
  let index = 0
  const answered: Route = { ...route }
  Object.defineProperty(answered, 'body', {
    enumerable: true,
    get() {
      const body = bodies[Math.min(index, bodies.length - 1)]
      index += 1
      return body
    },
  })
  return answered
}
