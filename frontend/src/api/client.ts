/**
 * Thin fetch wrapper around the Django API.
 *
 * Relative URLs throughout: Vite proxies /api to the backend in dev, and in
 * production both sit behind one origin, so no base-URL juggling is needed.
 */

export class ApiError extends Error {
  readonly status: number
  /** DRF field errors, e.g. { prn: ["No roster entry matches this PRN."] } */
  readonly fieldErrors: Record<string, string[]>
  /** Machine-readable cause some endpoints add next to `detail`, e.g. "prn_mismatch". */
  readonly reason: string

  constructor(
    status: number,
    message: string,
    fieldErrors: Record<string, string[]> = {},
    reason = '',
  ) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.fieldErrors = fieldErrors
    this.reason = reason
  }
}

const TOKEN_KEY = 'pcp.access'
const REFRESH_KEY = 'pcp.refresh'

export const tokenStore = {
  get access() {
    return localStorage.getItem(TOKEN_KEY)
  },
  get refresh() {
    return localStorage.getItem(REFRESH_KEY)
  },
  set(access: string, refresh: string) {
    localStorage.setItem(TOKEN_KEY, access)
    localStorage.setItem(REFRESH_KEY, refresh)
  },
  clear() {
    localStorage.removeItem(TOKEN_KEY)
    localStorage.removeItem(REFRESH_KEY)
  },
}

/**
 * Every message in one DRF error value, as plain text.
 *
 * DRF nests: a DictField or a field-level `ValidationError({...})` gives a
 * dict (the match filters do), a `many=True` child gives a list of dicts, a
 * ListField gives `{index: [...]}`. The inner key leads the message so it
 * still says which part is wrong.
 */
function flattenMessages(value: unknown): string[] {
  if (value === null || value === undefined) return []
  if (Array.isArray(value)) return value.flatMap(flattenMessages)
  if (typeof value === 'object') {
    return Object.entries(value as Record<string, unknown>).flatMap(([key, inner]) => {
      const label = /^\d+$/.test(key) ? `Item ${Number(key) + 1}` : key
      return flattenMessages(inner).map((message) => `${label}: ${message}`)
    })
  }
  return [String(value)]
}

/** Turn a DRF error body into a single readable sentence plus its field map. */
export function describeError(status: number, body: unknown): ApiError {
  const fallback = `Request failed (${status})`
  if (Array.isArray(body)) return new ApiError(status, flattenMessages(body)[0] ?? fallback)
  if (body && typeof body === 'object') {
    const record = body as Record<string, unknown>
    const detail = record.detail
    if (typeof detail === 'string') {
      const reason = typeof record.reason === 'string' ? record.reason : ''
      return new ApiError(status, detail, {}, reason)
    }

    const fieldErrors: Record<string, string[]> = {}
    for (const [key, value] of Object.entries(record)) {
      fieldErrors[key] = flattenMessages(value)
    }
    const first = Object.values(fieldErrors).find((messages) => messages.length)?.[0]
    return new ApiError(status, first ?? fallback, fieldErrors)
  }
  return new ApiError(status, fallback)
}

type RequestOptions = Omit<RequestInit, 'body'> & { body?: unknown; auth?: boolean }

export async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { body, auth = true, headers, ...rest } = options
  const isFormData = body instanceof FormData

  const finalHeaders = new Headers(headers)
  if (!isFormData && body !== undefined) finalHeaders.set('Content-Type', 'application/json')
  if (auth && tokenStore.access) {
    finalHeaders.set('Authorization', `Bearer ${tokenStore.access}`)
  }

  const response = await fetch(path, {
    ...rest,
    headers: finalHeaders,
    body: isFormData ? body : body !== undefined ? JSON.stringify(body) : undefined,
  })

  if (response.status === 204) return undefined as T

  const text = await response.text()
  const parsed = text ? JSON.parse(text) : null

  if (!response.ok) throw describeError(response.status, parsed)
  return parsed as T
}

export const api = {
  get: <T>(path: string, options?: RequestOptions) => request<T>(path, { ...options, method: 'GET' }),
  post: <T>(path: string, body?: unknown, options?: RequestOptions) =>
    request<T>(path, { ...options, method: 'POST', body }),
  patch: <T>(path: string, body?: unknown, options?: RequestOptions) =>
    request<T>(path, { ...options, method: 'PATCH', body }),
  delete: <T>(path: string, options?: RequestOptions) =>
    request<T>(path, { ...options, method: 'DELETE' }),
}
