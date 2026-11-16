import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'
import type { ReactNode } from 'react'

import { ApiError, tokenStore } from '@/api/client'
import { areaOf, authApi, storeSession, type AuthResult, type User } from '@/api/auth'

interface AuthState {
  user: User | null
  /** True until the stored token has been checked against the backend. */
  loading: boolean
  signIn: (result: AuthResult) => User
  signOut: () => void
  refreshUser: () => Promise<void>
}

const AuthContext = createContext<AuthState | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  // Only "loading" when there is actually a token to check, so a signed-out
  // visitor renders the page directly instead of flashing a spinner.
  const [loading, setLoading] = useState(() => Boolean(tokenStore.access))

  // A token in localStorage is a claim, not proof: it may be expired or
  // revoked, so the session is only real once /me answers.
  useEffect(() => {
    if (!tokenStore.access) return
    let cancelled = false
    authApi
      .me()
      .then((me) => !cancelled && setUser(me))
      .catch(() => {
        tokenStore.clear()
        if (!cancelled) setUser(null)
      })
      .finally(() => !cancelled && setLoading(false))
    return () => {
      cancelled = true
    }
  }, [])

  const signIn = useCallback((result: AuthResult) => {
    const signedIn = storeSession(result)
    setUser(signedIn)
    return signedIn
  }, [])

  const signOut = useCallback(() => {
    tokenStore.clear()
    setUser(null)
  }, [])

  const refreshUser = useCallback(async () => {
    try {
      setUser(await authApi.me())
    } catch (error) {
      if (error instanceof ApiError && error.status === 401) signOut()
    }
  }, [signOut])

  const value = useMemo(
    () => ({ user, loading, signIn, signOut, refreshUser }),
    [user, loading, signIn, signOut, refreshUser],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth(): AuthState {
  const context = useContext(AuthContext)
  if (!context) throw new Error('useAuth must be used inside <AuthProvider>')
  return context
}

/** Where each role lands after signing in. */
export function homePathFor(user: User): string {
  const area = areaOf(user)
  if (area === 'admin') return '/admin'
  if (area === 'company') return '/company'
  return '/student'
}

/**
 * Where to go after signing in, given the page that sent us to /login.
 *
 * `from` is honoured only inside the new user's own area: after a demo
 * persona switch, the page that redirected here may belong to another role,
 * and sending them there would only bounce them again.
 */
export function landingPathFor(user: User, from?: string | null): string {
  const home = homePathFor(user)
  if (from && from !== '/login' && (from === home || from.startsWith(`${home}/`))) return from
  return home
}
