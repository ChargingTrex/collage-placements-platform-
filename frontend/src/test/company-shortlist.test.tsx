import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { makeCompanyProfile } from '@/test/fixtures'
import { renderApp } from '@/test/harness'
import { COMPANY_USER, page, signedInAs } from '@/test/opportunity-fixtures'

const LIST = {
  path: '/api/profiles/students?shortlisted=true',
  body: page([makeCompanyProfile({ is_shortlisted: true })]),
}
const EMPTY = { path: '/api/profiles/students?shortlisted=true', body: page([]) }
const PASSWORD = 'Zk3-correct-horse-battery'

function zipBody(rows = 2) {
  return {
    password: PASSWORD,
    filename: 'shortlist-contacts.zip',
    zip_base64: btoa('PK-fake-zip-bytes'),
    row_count: rows,
  }
}

beforeEach(() => {
  localStorage.clear()
  sessionStorage.clear()
  URL.createObjectURL = vi.fn(() => 'blob:x')
  URL.revokeObjectURL = vi.fn()
})
afterEach(() => {
  vi.unstubAllGlobals()
  localStorage.clear()
  sessionStorage.clear()
})

describe('company shortlist', () => {
  it('lists the shortlisted students from the server filter', async () => {
    const fetchMock = signedInAs(COMPANY_USER, [LIST])
    renderApp('/company/shortlist')

    expect(await screen.findByText('Aarav Mehta')).toBeInTheDocument()
    expect(screen.getByText('1 student on your shortlist')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Shortlist' })).toBeInTheDocument()
    expect(
      fetchMock.mock.calls.some((c) => String(c[0]).includes('/students?shortlisted=true')),
    ).toBe(true)
  })

  it('has an empty state and both exports disabled', async () => {
    signedInAs(COMPANY_USER, [EMPTY])
    renderApp('/company/shortlist')

    expect(await screen.findByText('Your shortlist is empty')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Download CVs (zip)' })).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Export contacts' })).toBeDisabled()
  })

  it('downloads the CV zip with the bearer token and reports skipped students', async () => {
    const user = userEvent.setup()
    const fetchMock = signedInAs(COMPANY_USER, [
      {
        path: '/api/profiles/students/shortlist/resumes',
        headers: {
          'Content-Disposition': 'attachment; filename="shortlist-resumes.zip"',
          'X-Skipped-Without-Resume': '2',
        },
      },
      LIST,
    ])
    renderApp('/company/shortlist')

    await user.click(await screen.findByRole('button', { name: 'Download CVs (zip)' }))

    expect(await screen.findByText(/2 students had no resume and were skipped/)).toBeInTheDocument()
    expect(URL.createObjectURL).toHaveBeenCalled()
    const call = fetchMock.mock.calls.find((c) => String(c[0]).endsWith('/shortlist/resumes'))
    expect(new Headers(call?.[1]?.headers).get('Authorization')).toBe('Bearer access-token')
  })

  it('says nothing about skips when none were skipped', async () => {
    const user = userEvent.setup()
    signedInAs(COMPANY_USER, [
      {
        path: '/api/profiles/students/shortlist/resumes',
        headers: { 'X-Skipped-Without-Resume': '0' },
      },
      LIST,
    ])
    renderApp('/company/shortlist')

    await user.click(await screen.findByRole('button', { name: 'Download CVs (zip)' }))

    await waitFor(() => expect(URL.createObjectURL).toHaveBeenCalled())
    expect(screen.queryByText(/had no resume/)).not.toBeInTheDocument()
  })

  it('saves the contacts zip and shows the password once, only in the page', async () => {
    const user = userEvent.setup()
    const writeText = vi.fn(async () => undefined)
    Object.defineProperty(navigator, 'clipboard', { value: { writeText }, configurable: true })
    signedInAs(COMPANY_USER, [
      { path: '/api/profiles/students/shortlist/contacts', method: 'POST', body: zipBody(2) },
      LIST,
    ])
    renderApp('/company/shortlist')

    await user.click(await screen.findByRole('button', { name: 'Export contacts' }))

    const panel = await screen.findByRole('region', { name: 'Contacts export password' })
    expect(panel).toHaveTextContent(PASSWORD)
    expect(panel).toHaveTextContent('will not be shown again')
    expect(panel).toHaveTextContent('Saved shortlist-contacts.zip with 2 students')
    expect(panel).toHaveTextContent(/not been verified are included with blank email and phone/)
    expect(URL.createObjectURL).toHaveBeenCalled()

    await user.click(screen.getByRole('button', { name: 'Copy password' }))
    expect(writeText).toHaveBeenCalledWith(PASSWORD)

    // Never persisted anywhere.
    expect(JSON.stringify({ ...localStorage })).not.toContain(PASSWORD)
    expect(JSON.stringify({ ...sessionStorage })).not.toContain(PASSWORD)
    expect(window.location.href).not.toContain(PASSWORD)

    await user.click(screen.getByRole('button', { name: 'I have saved the password' }))
    expect(screen.queryByText(PASSWORD)).not.toBeInTheDocument()
  })

  it('loses the password when the page is left', async () => {
    const user = userEvent.setup()
    signedInAs(COMPANY_USER, [
      { path: '/api/profiles/students/shortlist/contacts', method: 'POST', body: zipBody(1) },
      LIST,
      { path: '/api/profiles/students/', body: makeCompanyProfile() },
    ])
    const { unmount } = renderApp('/company/shortlist')
    await user.click(await screen.findByRole('button', { name: 'Export contacts' }))
    await screen.findByText(PASSWORD)
    unmount()

    signedInAs(COMPANY_USER, [LIST])
    renderApp('/company/shortlist')
    await screen.findByText('Aarav Mehta')
    expect(screen.queryByText(PASSWORD)).not.toBeInTheDocument()
  })

  it('explains a 400 (too many rows) in plain words', async () => {
    const user = userEvent.setup()
    signedInAs(COMPANY_USER, [
      {
        path: '/api/profiles/students/shortlist/contacts',
        method: 'POST',
        status: 400,
        body: { detail: 'More than 500 rows.' },
      },
      LIST,
    ])
    renderApp('/company/shortlist')

    await user.click(await screen.findByRole('button', { name: 'Export contacts' }))

    expect(await screen.findByRole('alert')).toHaveTextContent(/too large to export in one go/i)
    expect(screen.queryByRole('region', { name: 'Contacts export password' })).not.toBeInTheDocument()
  })

  it('explains a 429 (throttled) in plain words', async () => {
    const user = userEvent.setup()
    signedInAs(COMPANY_USER, [
      {
        path: '/api/profiles/students/shortlist/contacts',
        method: 'POST',
        status: 429,
        body: { detail: 'Request was throttled.' },
      },
      LIST,
    ])
    renderApp('/company/shortlist')

    await user.click(await screen.findByRole('button', { name: 'Export contacts' }))

    expect(await screen.findByRole('alert')).toHaveTextContent(/exporting too often/i)
  })
})
