import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { downloadFile, filenameFromDisposition, openDocument } from '@/api/documents'

function stubFetch(headers: Record<string, string> = {}) {
  vi.stubGlobal(
    'fetch',
    vi.fn(async () => ({
      ok: true,
      status: 200,
      headers: new Headers(headers),
      text: async () => '',
      blob: async () => new Blob(['%PDF']),
    })),
  )
}

beforeEach(() => {
  URL.createObjectURL = vi.fn(() => 'blob:doc')
  URL.revokeObjectURL = vi.fn()
})
afterEach(() => {
  vi.unstubAllGlobals()
  vi.useRealTimers()
  vi.restoreAllMocks()
})

describe('filenameFromDisposition', () => {
  it('reads the quoted and the RFC 5987 forms, preferring the latter', () => {
    expect(filenameFromDisposition('attachment; filename="Aarav Mehta CV.pdf"')).toBe(
      'Aarav Mehta CV.pdf',
    )
    expect(filenameFromDisposition("attachment; filename*=UTF-8''r%C3%A9sum%C3%A9.pdf")).toBe(
      'résumé.pdf',
    )
    expect(
      filenameFromDisposition(
        `attachment; filename="resume.pdf"; filename*=UTF-8''r%C3%A9sum%C3%A9.pdf`,
      ),
    ).toBe('résumé.pdf')
  })

  it('returns null when there is nothing usable', () => {
    expect(filenameFromDisposition(null)).toBeNull()
    expect(filenameFromDisposition('inline')).toBeNull()
  })
})

describe('downloadFile', () => {
  function captureDownloadName() {
    const names: string[] = []
    vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(function (
      this: HTMLAnchorElement,
    ) {
      names.push(this.download)
    })
    return names
  }

  it('saves under the name from Content-Disposition', async () => {
    stubFetch({ 'Content-Disposition': 'attachment; filename="aarav_cv.pdf"' })
    const names = captureDownloadName()

    await downloadFile('/api/profiles/me/resume', 'fallback.pdf')

    expect(names).toEqual(['aarav_cv.pdf'])
    expect(URL.revokeObjectURL).toHaveBeenCalledWith('blob:doc')
  })

  it('falls back to the caller-supplied name without the header', async () => {
    stubFetch()
    const names = captureDownloadName()

    await downloadFile('/api/profiles/me/resume', 'fallback.pdf')

    expect(names).toEqual(['fallback.pdf'])
  })
})

describe('openDocument', () => {
  it('revokes its blob URL later, not while the tab is still loading it', async () => {
    vi.useFakeTimers()
    stubFetch()
    const tab = { location: { href: '' }, close: vi.fn() }
    vi.stubGlobal('open', vi.fn(() => tab))

    await openDocument('/api/profiles/me/resume')

    expect(tab.location.href).toBe('blob:doc')
    expect(URL.revokeObjectURL).not.toHaveBeenCalled()
    vi.advanceTimersByTime(60_000)
    expect(URL.revokeObjectURL).toHaveBeenCalledWith('blob:doc')
  })
})
