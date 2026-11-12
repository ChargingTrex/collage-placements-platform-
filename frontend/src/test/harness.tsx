import { render } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { vi } from 'vitest'

import App from '@/App'

/** One handler per path prefix; first match wins. */
export interface Route {
  path: string
  /** Match only this HTTP method. Omitted, the route answers any method. */
  method?: string
  status?: number
  body?: unknown
  /** Response headers, e.g. Content-Disposition. */
  headers?: Record<string, string>
  /** Called with the parsed request so a test can assert what was sent. */
  onCall?: (init: { method: string; body: unknown; authorization: string | null }) => void
}

export function mockApi(routes: Route[]) {
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input)
    const method = init?.method ?? 'GET'
    const route = routes.find(
      (candidate) =>
        url.startsWith(candidate.path) &&
        (candidate.method === undefined || candidate.method === method),
    )

    if (!route) {
      return {
        ok: false,
        status: 404,
        text: async () => JSON.stringify({ detail: `No mock for ${url}` }),
      } as Response
    }

    route.onCall?.({
      method,
      body: typeof init?.body === 'string' ? JSON.parse(init.body) : init?.body,
      authorization: new Headers(init?.headers).get('Authorization'),
    })

    const status = route.status ?? 200
    return {
      ok: status >= 200 && status < 300,
      status,
      headers: new Headers(route.headers),
      text: async () => JSON.stringify(route.body ?? {}),
      blob: async () => new Blob([JSON.stringify(route.body ?? {})]),
    } as Response
  })

  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

export const HEALTHY = {
  path: '/api/health',
  body: {
    status: 'ok',
    service: 'placement-cell-portal',
    debug: true,
    checks: {
      database: { ok: true, engine: 'sqlite' },
      storage: { ok: true, backend: 'local' },
      matching_engine: { ok: true, backend: 'spacy', detail: 'en_core_web_md' },
    },
  },
} satisfies Route

export function makeUser(overrides: Record<string, unknown> = {}) {
  return {
    id: 'u-1',
    email: 'aarav.mehta@college.edu',
    prn: '220200901',
    full_name: 'Aarav Mehta',
    roles: ['student'],
    status: 'active',
    is_verified: true,
    has_usable_password: true,
    date_joined: '2026-09-01T00:00:00Z',
    ...overrides,
    // Follows full_name unless a test sets it, so a test that renames the user
    // does not leave the header showing somebody else.
    display_name: (overrides.display_name ?? overrides.full_name ?? 'Aarav Mehta') as string,
  }
}

export function makeAuthResult(overrides: Record<string, unknown> = {}) {
  return {
    user: makeUser(overrides),
    tokens: { access: 'access-token', refresh: 'refresh-token' },
  }
}

export function renderApp(initialPath = '/') {
  return render(
    <MemoryRouter initialEntries={[initialPath]}>
      <App />
    </MemoryRouter>,
  )
}
