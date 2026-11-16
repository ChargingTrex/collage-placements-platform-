import { api } from '@/api/client'
import type { Paginated } from '@/api/roster'

/** Pages are 20 rows, so this reaches 500 rows before it stops and says so. */
export const MAX_PAGES = 25

/** Every row the server would give, up to MAX_PAGES, and the server's own total. */
export interface Collected<T> {
  rows: T[]
  /** The server's `count`: how many rows exist, not how many were fetched. */
  count: number
  /** True when the bound stopped the fetch before the last page. Never silent. */
  truncated: boolean
}

/**
 * `next` is an absolute URL on the API's own origin. Behind the dev proxy that
 * origin is not one the browser can reach, so only its path and query are used.
 */
export function pathOf(next: string): string {
  try {
    const url = new URL(next, 'http://placeholder.invalid')
    return `${url.pathname}${url.search}`
  } catch {
    return next
  }
}

/** Follow `next` until it runs out, or until `maxPages` pages have been read. */
export async function fetchAll<T>(firstPath: string, maxPages = MAX_PAGES): Promise<Collected<T>> {
  const rows: T[] = []
  let count = 0
  let path: string | null = firstPath
  let pages = 0
  while (path && pages < maxPages) {
    const body: Paginated<T> | T[] = await api.get<Paginated<T> | T[]>(path)
    pages += 1
    if (Array.isArray(body)) {
      // An unpaginated endpoint: the array is everything.
      return { rows: body, count: body.length, truncated: false }
    }
    rows.push(...body.results)
    count = body.count
    path = body.next ? pathOf(body.next) : null
  }
  return { rows, count: Math.max(count, rows.length), truncated: path !== null }
}

/** The "Showing the first N of M" facts, or null when everything arrived. */
export function truncationOf(collected: Collected<unknown>): { shown: number; total: number } | null {
  return collected.truncated ? { shown: collected.rows.length, total: collected.count } : null
}
