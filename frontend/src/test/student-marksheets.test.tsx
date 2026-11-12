import '@testing-library/jest-dom/vitest'
import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { makeOwnProfile } from '@/test/fixtures'
import { HEALTHY, makeUser, mockApi, renderApp, type Route } from '@/test/harness'

/** `extra` first: later routes win only if listed ahead of the catch-all. */
function signedInAsStudent(extra: Route[] = []) {
  localStorage.setItem('pcp.access', 'access-token')
  return mockApi([
    HEALTHY,
    { path: '/api/auth/me', body: makeUser() },
    ...extra,
    { path: '/api/profiles/me', body: makeOwnProfile() },
  ])
}

const PDF = new File(['%PDF-1.4'], 'class10.pdf', { type: 'application/pdf' })
const PHOTO = new File(['\xff\xd8\xff'], 'class12.jpg', { type: 'image/jpeg' })

async function openCard(name: string) {
  const heading = await screen.findByRole('heading', { name })
  return heading.closest('section') as HTMLElement
}

beforeEach(() => localStorage.clear())
afterEach(() => {
  vi.unstubAllGlobals()
  localStorage.clear()
})

describe('school marksheets', () => {
  it('offers a separate entry for each of class 10 and class 12', async () => {
    signedInAsStudent()
    renderApp('/student/profile')
    const card = await openCard('School results')

    expect(within(card).getByRole('heading', { name: 'Class 10' })).toBeInTheDocument()
    expect(within(card).getByRole('heading', { name: 'Class 12' })).toBeInTheDocument()
  })

  it('uploads a marksheet to the level it belongs to', async () => {
    const user = userEvent.setup()
    const urls: string[] = []
    signedInAsStudent([
      {
        path: '/api/profiles/me/marksheet/10',
        method: 'POST',
        body: makeOwnProfile({
          marksheet_10_url: '/api/profiles/me/marksheet/10/file',
          marksheet_10_filename: 'class10.pdf',
        }),
        onCall: () => urls.push('10'),
      },
    ])
    renderApp('/student/profile')
    const card = await openCard('School results')

    await user.upload(within(card).getByLabelText('Upload Class 10 marksheet'), PDF)
    await user.click(within(card).getAllByRole('button', { name: 'Upload' })[0])

    await waitFor(() => expect(urls).toEqual(['10']))
    expect(await within(card).findByText('class10.pdf')).toBeInTheDocument()
  })

  it('accepts a photographed marksheet, not only a PDF', async () => {
    const user = userEvent.setup()
    const sent: string[] = []
    signedInAsStudent([
      {
        path: '/api/profiles/me/marksheet/12',
        method: 'POST',
        body: makeOwnProfile({ marksheet_12_filename: 'class12.jpg' }),
        onCall: () => sent.push('12'),
      },
    ])
    renderApp('/student/profile')
    const card = await openCard('School results')

    await user.upload(within(card).getByLabelText('Upload Class 12 marksheet'), PHOTO)
    await user.click(within(card).getAllByRole('button', { name: 'Upload' })[1])

    await waitFor(() => expect(sent).toEqual(['12']))
  })

  it('saves the marks as their own step, separate from the file', async () => {
    const user = userEvent.setup()
    const bodies: unknown[] = []
    signedInAsStudent([
      {
        path: '/api/profiles/me',
        method: 'PATCH',
        body: makeOwnProfile({ marks_10_percentage: '92.40', marks_10_board: 'cbse' }),
        onCall: ({ body }) => bodies.push(body),
      },
    ])
    renderApp('/student/profile')
    const card = await openCard('School results')
    const ten = within(card).getByRole('heading', { name: 'Class 10' }).closest('section')!

    await user.type(within(ten).getByLabelText('Percentage'), '92.40')
    await user.selectOptions(within(ten).getByLabelText('Board'), 'cbse')
    await user.type(within(ten).getByLabelText('Year of passing'), '2020')
    await user.click(within(ten).getByRole('button', { name: 'Save Class 10 marks' }))

    await waitFor(() =>
      expect(bodies).toEqual([
        { marks_10_percentage: '92.40', marks_10_board: 'cbse', marks_10_year: 2020 },
      ]),
    )
  })

  it('surfaces a rejected file type', async () => {
    const user = userEvent.setup()
    signedInAsStudent([
      {
        path: '/api/profiles/me/marksheet/10',
        method: 'POST',
        status: 400,
        body: { file: ["Unsupported file type '.docx'. Allowed: .jpeg, .jpg, .pdf, .png."] },
      },
    ])
    renderApp('/student/profile')
    const card = await openCard('School results')

    await user.upload(within(card).getByLabelText('Upload Class 10 marksheet'), PDF)
    await user.click(within(card).getAllByRole('button', { name: 'Upload' })[0])

    expect(await within(card).findByText(/Unsupported file type/)).toBeInTheDocument()
  })
})

describe('the student states their own CGPA', () => {
  it('is its own entry, usable with no transcript uploaded', async () => {
    const user = userEvent.setup()
    const bodies: unknown[] = []
    signedInAsStudent([
      {
        path: '/api/profiles/me/confirm-cgpa',
        method: 'POST',
        body: makeOwnProfile({ confirmed_cgpa: '8.50' }),
        onCall: ({ body }) => bodies.push(body),
      },
    ])
    renderApp('/student/profile')
    const card = await openCard('Your CGPA')

    // No transcript on this fixture, and the field is still here.
    await user.type(within(card).getByLabelText('CGPA'), '8.50')
    await user.click(within(card).getByRole('button', { name: 'Save CGPA' }))

    await waitFor(() => expect(bodies).toEqual([{ cgpa: '8.50' }]))
    expect(await within(card).findByText('Saved.')).toBeInTheDocument()
  })

  it('says so when the stated figure differs from the transcript', async () => {
    signedInAsStudent([
      {
        path: '/api/profiles/me',
        body: makeOwnProfile({ parsed_cgpa: '8.40', confirmed_cgpa: '9.90' }),
      },
    ])
    renderApp('/student/profile')
    const card = await openCard('Your CGPA')

    expect(within(card).getByText('This differs from your transcript')).toBeInTheDocument()
    expect(within(card).getByText(/8\.40/)).toBeInTheDocument()
  })

  it('does not nag when the two agree', async () => {
    signedInAsStudent([
      {
        path: '/api/profiles/me',
        body: makeOwnProfile({ parsed_cgpa: '8.40', confirmed_cgpa: '8.40' }),
      },
    ])
    renderApp('/student/profile')
    const card = await openCard('Your CGPA')

    expect(within(card).queryByText('This differs from your transcript')).not.toBeInTheDocument()
  })

  it('surfaces an out-of-range value from the server', async () => {
    const user = userEvent.setup()
    signedInAsStudent([
      {
        path: '/api/profiles/me/confirm-cgpa',
        method: 'POST',
        status: 400,
        body: { cgpa: ['Ensure this value is less than or equal to 10.'] },
      },
    ])
    renderApp('/student/profile')
    const card = await openCard('Your CGPA')

    await user.type(within(card).getByLabelText('CGPA'), '99')
    await user.click(within(card).getByRole('button', { name: 'Save CGPA' }))

    expect(await within(card).findByText(/less than or equal to 10/)).toBeInTheDocument()
  })
})
