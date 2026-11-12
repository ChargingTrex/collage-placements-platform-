import { api, ApiError } from '@/api/client'
import type { CompanyProfile } from '@/api/profiles'
import type { Paginated } from '@/api/roster'

export type MatchComponentName = 'semantic' | 'skills' | 'experience' | 'education'

export interface MatchComponent {
  /** 0-1. */
  score: number
  /** The share of the total this part carried, 0-1. Zero when it was not counted. */
  weight: number
  /** The uncalibrated similarity; semantic only. */
  raw?: number
}

/**
 * One profile against one job description. A match, not a probability: the
 * breakdown always travels with the number.
 */
export interface MatchScore {
  /** 0-100. */
  score: number
  components: Record<MatchComponentName, MatchComponent>
  matched_skills: string[]
  missing_skills: string[]
  hard_filter_failures: string[]
  flagged: boolean
  semantic_source: string
}

/** What the server read the JD as asking for. Never the JD text back. */
export interface JobSummary {
  canonical_role: string | null
  required_skills: string[]
  min_experience_years: number | null
  education_levels: string[]
  source: 'llm' | 'text'
}

export interface MatchResult extends CompanyProfile {
  categories: string[]
  match: MatchScore
}

export interface MatchSearchResponse {
  count: number
  /** True when no vector index was used and visible profiles were scored directly. */
  fallback: boolean
  job: JobSummary
  results: MatchResult[]
}

export interface RoleCategory {
  name: string
  jd_count: number
  top_skills: string[]
}

type FilterValue = string | number
export type FilterCondition =
  | FilterValue
  | { in: FilterValue[] }
  | { gte?: number; lte?: number }

/** The vector store's filter dialect. An unknown key is a 400 on the server. */
export type MatchFilters = Partial<
  Record<
    'department' | 'batch' | 'education_level' | 'experience_months' | 'skills' | 'categories',
    FilterCondition
  >
>

export const JD_MIN_CHARS = 30

/** A runaway `next` must not spin the page: 10 pages is 200 categories. */
export const CATEGORY_PAGE_CAP = 10

/** The path of a DRF `next` link. Its host is the server's view of itself, not this page's. */
function samePath(link: string): string {
  const url = new URL(link, window.location.origin)
  return `${url.pathname}${url.search}`
}

/**
 * Every role category, following `next` page by page. A name seen on an
 * earlier page is kept once: a category added mid-walk shifts the pages.
 */
async function allCategories(): Promise<RoleCategory[]> {
  const byName = new Map<string, RoleCategory>()
  let path: string | null = '/api/matching/categories'
  for (let page = 0; path && page < CATEGORY_PAGE_CAP; page += 1) {
    const body: Paginated<RoleCategory> = await api.get<Paginated<RoleCategory>>(path)
    for (const category of body.results) {
      if (!byName.has(category.name)) byName.set(category.name, category)
    }
    path = body.next ? samePath(body.next) : null
  }
  return [...byName.values()]
}

export const matchingApi = {
  search: (jdText: string, filters: MatchFilters = {}, k = 20) =>
    api.post<MatchSearchResponse>('/api/matching/search', { jd_text: jdText, k, filters }),
  score: (jdText: string, studentIds: string[]) =>
    api.post<Omit<MatchSearchResponse, 'fallback'>>('/api/matching/score', {
      jd_text: jdText,
      student_ids: studentIds,
    }),
  categories: allCategories,
}

/**
 * A sentence for a failed matching call. The `matching` throttle is shared by
 * search, score, own match and resume analysis, so a 429 says when to retry
 * rather than DRF's "Request was throttled".
 */
export function describeMatchingError(caught: unknown, fallback: string): string {
  if (!(caught instanceof ApiError)) return fallback
  if (caught.status === 429) {
    const seconds = Number(/(\d+)\s+seconds?/.exec(caught.message)?.[1])
    const wait =
      Number.isFinite(seconds) && seconds > 0
        ? ` Try again in about ${Math.max(1, Math.ceil(seconds / 60))} minute${seconds > 60 ? 's' : ''}.`
        : ' Try again later.'
    return `You have run the matcher too many times in the last hour.${wait}`
  }
  return caught.message || fallback
}
