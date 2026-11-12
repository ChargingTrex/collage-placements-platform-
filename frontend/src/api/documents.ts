import { describeError, tokenStore } from '@/api/client'

/**
 * Resumes and transcripts are served by authenticated API endpoints, not as
 * public /media/ links, so a plain <a href> would arrive without the bearer
 * token and get a 401. Fetch with the token, then show the bytes from a
 * blob URL.
 */
async function fetchAuthed(url: string): Promise<Response> {
  const headers = new Headers()
  if (tokenStore.access) headers.set('Authorization', `Bearer ${tokenStore.access}`)
  return fetch(url, { headers })
}

async function failure(response: Response, notFound: string): Promise<Error> {
  if (response.status === 404) return new Error(notFound)
  let body: unknown = null
  try {
    body = JSON.parse(await response.text())
  } catch {
    // Not JSON; the status is all there is.
  }
  return describeError(response.status, body)
}

const REVOKE_AFTER_MS = 60_000

/** Open an authenticated file in a new tab. Throws an Error with a readable message. */
export async function openDocument(url: string): Promise<void> {
  // The tab is opened before the fetch: browsers only allow a new tab from a
  // click, not from after an await.
  const tab = window.open('', '_blank')
  try {
    const response = await fetchAuthed(url)
    if (!response.ok) throw await failure(response, 'This document is no longer available.')
    const objectUrl = URL.createObjectURL(await response.blob())
    if (tab) tab.location.href = objectUrl
    else window.open(objectUrl, '_blank')
    // Not revoked at once: the new tab loads the blob after this returns, and
    // a revoked URL would show an empty page. A minute is ample for the load.
    setTimeout(() => URL.revokeObjectURL(objectUrl), REVOKE_AFTER_MS)
  } catch (caught) {
    tab?.close()
    throw caught instanceof Error ? caught : new Error('Could not open the document.')
  }
}

/**
 * The name the server sent in Content-Disposition. Prefers the RFC 5987
 * `filename*=UTF-8''...` form (non-ASCII names) over plain `filename="..."`.
 */
export function filenameFromDisposition(header: string | null | undefined): string | null {
  if (!header) return null
  const extended = /filename\*\s*=\s*([^']*)'[^']*'([^;]+)/i.exec(header)
  if (extended) {
    try {
      const name = decodeURIComponent(extended[2].trim())
      if (name) return name
    } catch {
      // Malformed escape; fall through to the plain form.
    }
  }
  const plain = /filename\s*=\s*(?:"((?:[^"\\]|\\.)*)"|([^;]+))/i.exec(header)
  const name = (plain?.[1]?.replace(/\\(.)/g, '$1') ?? plain?.[2] ?? '').trim()
  return name || null
}

/**
 * Save an authenticated file through the bearer fetch. The server's
 * Content-Disposition name wins; `fallbackName` covers a missing header.
 */
export async function downloadFile(url: string, fallbackName: string): Promise<void> {
  const response = await fetchAuthed(url)
  if (!response.ok) throw await failure(response, 'Nothing to download.')
  const filename =
    filenameFromDisposition(response.headers?.get('Content-Disposition')) ?? fallbackName
  const objectUrl = URL.createObjectURL(await response.blob())
  const link = document.createElement('a')
  link.href = objectUrl
  link.download = filename
  document.body.appendChild(link)
  link.click()
  link.remove()
  URL.revokeObjectURL(objectUrl)
}
