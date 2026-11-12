import { api, tokenStore } from '@/api/client'

/** The three areas of the app. Derived from `roles`, never read from the token directly. */
export type Role = 'student' | 'admin' | 'company'

export interface User {
  id: string
  email: string
  prn: string | null
  full_name: string
  display_name: string
  /** Plural and a list: `placement_admin`, `student`, `company_recruiter:<uuid>`. */
  roles: string[]
  status: string
  is_verified: boolean
  has_usable_password: boolean
  date_joined: string
}

export interface AuthResult {
  user: User
  tokens: { access: string; refresh: string }
}

export interface OtpIssued {
  detail: string
  expires_at: string
  /** Present only while the backend runs with DEBUG and EXPOSE_OTP_IN_RESPONSE. */
  debug_otp?: string
  prn?: string
  email?: string
}

export const authApi = {
  signup: (prn: string, email: string) => api.post<OtpIssued>('/api/auth/signup', { prn, email }, { auth: false }),

  verify: (identifier: string, code: string, password: string) =>
    api.post<AuthResult>('/api/auth/verify', { identifier, code, password }, { auth: false }),

  login: (identifier: string, password: string) =>
    api.post<AuthResult>('/api/auth/login', { identifier, password }, { auth: false }),

  requestOtp: (identifier: string) =>
    api.post<OtpIssued>('/api/auth/otp/request', { identifier }, { auth: false }),

  otpLogin: (identifier: string, code: string) =>
    api.post<AuthResult>('/api/auth/otp/login', { identifier, code }, { auth: false }),

  me: () => api.get<User>('/api/auth/me'),
}

export function storeSession(result: AuthResult): User {
  tokenStore.set(result.tokens.access, result.tokens.refresh)
  return result.user
}

/**
 * Which area of the app a user belongs to.
 *
 * The token carries institution-wide role names (`placement_admin`) and scoped
 * ones (`company_recruiter:<company_uuid>`), so routing has to translate them
 * rather than compare strings. Admin wins if somebody somehow holds both,
 * because the more privileged area is the safer one to land on.
 */
export function areaOf(user: Pick<User, 'roles'>): Role {
  const roles = user.roles ?? []
  if (roles.includes('placement_admin')) return 'admin'
  if (roles.some((role) => role === 'company_recruiter' || role.startsWith('company_recruiter:'))) {
    return 'company'
  }
  return 'student'
}
