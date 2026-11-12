import type { ReactNode } from 'react'
import { Navigate, useLocation } from 'react-router-dom'

import { areaOf, type Role } from '@/api/auth'
import { homePathFor, useAuth } from '@/auth/AuthContext'

function Checking() {
  return <p className="px-6 py-16 text-center text-sm text-ink-400">Checking your session…</p>
}

/**
 * Route guards are a convenience, not the security boundary -- every endpoint
 * behind them enforces the same rule server-side.
 */
export function RequireAuth({ children }: { children: ReactNode }) {
  const { user, loading } = useAuth()
  const location = useLocation()

  if (loading) return <Checking />
  if (!user) return <Navigate to="/login" state={{ from: location.pathname }} replace />
  return <>{children}</>
}

export function RequireRole({ role, children }: { role: Role; children: ReactNode }) {
  const { user, loading } = useAuth()
  const location = useLocation()

  if (loading) return <Checking />
  if (!user) return <Navigate to="/login" state={{ from: location.pathname }} replace />
  if (areaOf(user) !== role) return <Navigate to={homePathFor(user)} replace />
  return <>{children}</>
}

export function RedirectIfSignedIn({ children }: { children: ReactNode }) {
  const { user, loading } = useAuth()

  if (loading) return <Checking />
  if (user) return <Navigate to={homePathFor(user)} replace />
  return <>{children}</>
}
