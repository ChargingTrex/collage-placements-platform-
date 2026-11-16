import { useEffect, useState, type ReactNode } from 'react'
import { NavLink, useNavigate } from 'react-router-dom'

import { areaOf } from '@/api/auth'
import { NOTIFICATIONS_CHANGED, notificationsApi } from '@/api/notifications'
import { Badge, Button } from '@/components/ui'
import { homePathFor, useAuth } from '@/auth/AuthContext'

const NAV_BY_ROLE = {
  student: [
    { to: '/student', label: 'Dashboard', end: true },
    { to: '/student/profile', label: 'My profile' },
    { to: '/student/jobs', label: 'Jobs' },
    { to: '/student/suggestions', label: 'Suggestions' },
    { to: '/student/applications', label: 'My applications' },
    { to: '/student/notifications', label: 'Notifications' },
  ],
  admin: [
    { to: '/admin', label: 'Dashboard', end: true },
    { to: '/admin/roster', label: 'Roster' },
    { to: '/admin/flagged', label: 'Flagged signups' },
    { to: '/admin/profiles', label: 'Profiles' },
    { to: '/admin/outcomes', label: 'Outcomes' },
    { to: '/admin/users', label: 'All users' },
    { to: '/admin/opportunities', label: 'Postings', end: true },
    { to: '/admin/opportunities/review', label: 'Review queue' },
    { to: '/admin/opportunities/stats', label: 'Posting figures' },
  ],
  company: [
    { to: '/company', label: 'Dashboard', end: true },
    { to: '/company/students', label: 'Browse students' },
    { to: '/company/opportunities', label: 'My postings' },
    { to: '/company/shortlist', label: 'Shortlist' },
  ],
} as const

const ROLE_LABEL = {
  student: 'Student',
  admin: 'Placement cell',
  company: 'Recruiter',
} as const

export default function AppShell({ children }: { children: ReactNode }) {
  const { user, signOut } = useAuth()
  const navigate = useNavigate()
  const [unread, setUnread] = useState(0)
  const isStudent = user ? areaOf(user) === 'student' : false

  // Only students receive notifications (D26). A failed count just hides the badge.
  useEffect(() => {
    if (!isStudent) return
    let cancelled = false
    const refresh = () =>
      notificationsApi
        .unreadCount()
        .then((count) => !cancelled && setUnread(count))
        .catch(() => !cancelled && setUnread(0))
    void refresh()
    window.addEventListener(NOTIFICATIONS_CHANGED, refresh)
    return () => {
      cancelled = true
      window.removeEventListener(NOTIFICATIONS_CHANGED, refresh)
    }
  }, [isStudent])

  if (!user) return <>{children}</>

  const area = areaOf(user)
  const links = NAV_BY_ROLE[area]

  return (
    <div className="min-h-full">
      <header className="border-b border-ink-200 bg-white">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center gap-x-6 gap-y-3 px-6 py-3">
          <NavLink to={homePathFor(user)} className="font-semibold tracking-tight">
            Placement&nbsp;Cell
          </NavLink>

          <nav className="flex flex-wrap items-center gap-1 text-sm">
            {links.map((link) => (
              <NavLink
                key={link.to}
                to={link.to}
                end={'end' in link ? link.end : undefined}
                className={({ isActive }) =>
                  `rounded-md px-3 py-1.5 transition ${
                    isActive ? 'bg-brand-50 font-medium text-brand-700' : 'text-ink-600 hover:bg-ink-100'
                  }`
                }
              >
                {link.label}
                {link.to === '/student/notifications' && unread > 0 ? (
                  <span className="ml-1.5 rounded-full bg-brand-600 px-1.5 py-0.5 text-xs text-white">
                    <span aria-hidden>{unread}</span>
                    <span className="sr-only">{unread} unread</span>
                  </span>
                ) : null}
              </NavLink>
            ))}
          </nav>

          <div className="ml-auto flex items-center gap-3">
            <div className="hidden text-right sm:block">
              <p className="text-sm font-medium">{user.display_name || user.full_name || user.email}</p>
              <p className="text-xs text-ink-400">{user.prn ?? user.email}</p>
            </div>
            <Badge tone="brand">{ROLE_LABEL[area]}</Badge>
            <Button
              variant="ghost"
              size="sm"
              onClick={() => {
                signOut()
                navigate('/login', { replace: true })
              }}
            >
              Sign out
            </Button>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-6xl px-6 py-8">{children}</main>
    </div>
  )
}

/** Centred card layout for the signed-out screens. */
export function AuthLayout({
  title,
  subtitle,
  children,
  footer,
}: {
  title: string
  subtitle?: string
  children: ReactNode
  footer?: ReactNode
}) {
  return (
    <div className="flex min-h-full items-center justify-center px-6 py-12">
      <div className="w-full max-w-md">
        <p className="text-xs font-semibold tracking-widest text-brand-600 uppercase">
          Placement Cell Portal
        </p>
        <h1 className="mt-2 text-2xl font-semibold tracking-tight">{title}</h1>
        {subtitle ? <p className="mt-1 text-sm text-ink-600">{subtitle}</p> : null}

        <div className="mt-6 rounded-xl border border-ink-200 bg-white p-6">{children}</div>

        {footer ? <div className="mt-4 text-center text-sm text-ink-600">{footer}</div> : null}
      </div>
    </div>
  )
}
