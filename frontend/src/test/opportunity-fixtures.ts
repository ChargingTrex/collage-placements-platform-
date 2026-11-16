import type { AppNotification } from '@/api/notifications'
import type {
  CompanyApplication,
  FeedRow,
  Opportunity,
  StudentApplication,
} from '@/api/opportunities'
import { HEALTHY, makeUser, mockApi, type Route } from '@/test/harness'

/** Sign in as `user` and mock the API. Routes are matched first to last by path prefix. */
export function signedInAs(user: ReturnType<typeof makeUser>, extra: Route[] = []) {
  localStorage.setItem('pcp.access', 'access-token')
  return mockApi([HEALTHY, { path: '/api/auth/me', body: user }, ...extra])
}

export const COMPANY_USER = makeUser({
  roles: ['company_recruiter:7a1b2c3d-0000-4000-8000-00000000c0de'],
  prn: null,
  email: 'recruiter@acmetech.example',
  full_name: 'Acme Tech',
})

export const ADMIN_USER = makeUser({
  roles: ['placement_admin'],
  prn: null,
  email: 'placement.officer@college.edu',
  full_name: 'Priya Kulkarni',
})

export const OPP_ID = '9b1d0a52-1111-4a6c-8f00-000000000001'

export function makeOpportunity(overrides: Partial<Opportunity> = {}): Opportunity {
  return {
    id: OPP_ID,
    company: '7a1b2c3d-0000-4000-8000-00000000c0de',
    company_name: 'Acme Tech',
    title: 'Backend Engineer',
    description: 'Build Django services.',
    role_type: 'full_time',
    location: 'Pune',
    openings: 2,
    required_skills: ['python', 'django'],
    eligible_departments: [],
    min_cgpa: 7,
    min_experience_years: null,
    required_education_levels: [],
    salary_disclosed: true,
    salary_min: 600000,
    salary_max: 900000,
    salary_period: 'year',
    salary_currency: 'INR',
    deadline: '2026-12-31',
    similarity_threshold: null,
    status: 'draft',
    ...overrides,
  }
}

export function makeFeedRow(overrides: Partial<FeedRow> = {}): FeedRow {
  const component = { score: 0.7, weight: 0.25 }
  return {
    ...makeOpportunity({ status: 'open' }),
    score: 72,
    components: {
      semantic: component,
      skills: component,
      cgpa: component,
      experience: component,
      projects: component,
      education: component,
    } as unknown as FeedRow['components'],
    matched_skills: ['python'],
    missing_skills: ['django'],
    eligible: true,
    eligibility_reasons: [],
    has_applied: false,
    application_status: null,
    ...overrides,
  }
}

export function makeCompanyApplication(
  overrides: Partial<CompanyApplication> = {},
): CompanyApplication {
  return {
    id: 'app-1',
    status: 'applied',
    applied_at: '2026-11-01T10:00:00Z',
    score: 81,
    similarity: 0.62,
    eligible: true,
    eligibility_reasons: [],
    opportunity: { id: OPP_ID, title: 'Backend Engineer' },
    prn: '220200901',
    full_name: 'Aarav Mehta',
    department: 'Computer Engineering',
    programme: 'B.Tech Computer Engineering',
    school: 'Engineering',
    batch: 2026,
    year_of_study: 4,
    cgpa_at_apply: '8.72',
    skills: ['Python', 'Django'],
    resume_url: '/api/opportunities/applications/app-1/resume',
    contact: null,
    contact_available: false,
    ...overrides,
  }
}

export function makeStudentApplication(
  overrides: Partial<StudentApplication> = {},
): StudentApplication {
  return {
    ...makeCompanyApplication(),
    events: [
      { from_status: '', to_status: 'applied', note: '', created_at: '2026-11-01T10:00:00Z' },
    ],
    ...overrides,
  }
}

export function makeNotification(overrides: Partial<AppNotification> = {}): AppNotification {
  return {
    id: 'n-1',
    kind: 'new_opportunity',
    opportunity: { id: OPP_ID, title: 'Backend Engineer' },
    created_at: '2026-11-01T10:00:00Z',
    read_at: null,
    ...overrides,
  }
}

export function page<T>(results: T[]) {
  return { count: results.length, next: null, previous: null, results }
}
