import { screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { HEALTHY, mockApi, renderApp } from '@/test/harness'

afterEach(() => {
  vi.unstubAllGlobals()
  localStorage.clear()
})

describe('landing page', () => {
  it('renders the pitch and both entry points to a signed-out visitor', async () => {
    mockApi([HEALTHY])
    renderApp('/')

    expect(
      screen.getByRole('heading', { name: /everything a placement drive needs/i }),
    ).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /create your student account/i })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /sign in/i })).toBeInTheDocument()
  })

  it('shows live backend status once /api/health answers', async () => {
    mockApi([HEALTHY])
    renderApp('/')

    await waitFor(() => expect(screen.getByText(/backend ok/i)).toBeInTheDocument())
    expect(screen.getByText('en_core_web_md')).toBeInTheDocument()
  })

  it('says the backend is unreachable rather than rendering a blank panel', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('Failed to fetch')))
    renderApp('/')

    await waitFor(() => expect(screen.getByText(/backend unreachable/i)).toBeInTheDocument())
  })
})
