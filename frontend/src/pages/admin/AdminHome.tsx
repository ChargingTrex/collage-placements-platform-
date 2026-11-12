import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'

import { profilesApi } from '@/api/profiles'
import { rosterApi } from '@/api/roster'
import { Card, CardTitle, PageHeader } from '@/components/ui'
import { useAuth } from '@/auth/AuthContext'

export default function AdminHome() {
  const { user } = useAuth()
  const [counts, setCounts] = useState<{ students: number; openFlags: number } | null>(null)

  const [onboarded, setOnboarded] = useState<number | null>(null)

  // Separate from the roster counts so one failing does not blank the other.
  useEffect(() => {
    let cancelled = false
    profilesApi
      .adminStats()
      .then((stats) => !cancelled && setOnboarded(stats.onboarding_completed ?? null))
      .catch(() => undefined)
    return () => {
      cancelled = true
    }
  }, [])

  useEffect(() => {
    let cancelled = false
    Promise.all([rosterApi.students(), rosterApi.flagged({ status: 'open' })])
      .then(([students, flagged]) => {
        if (!cancelled) setCounts({ students: students.count, openFlags: flagged.count })
      })
      .catch(() => !cancelled && setCounts(null))
    return () => {
      cancelled = true
    }
  }, [])

  return (
    <>
      <PageHeader
        title={`Welcome, ${user?.full_name || 'placement cell'}`}
        subtitle="Roster, verification, and the signup review queue."
      />

      <div className="grid gap-4 sm:grid-cols-2">
        <Link to="/admin/roster" className="block transition hover:opacity-80">
          <Card>
            <CardTitle hint="Upload and browse the student master list.">Roster</CardTitle>
            <p className="text-3xl font-semibold tabular-nums">{counts?.students ?? '—'}</p>
            <p className="text-sm text-ink-600">students on the roster</p>
          </Card>
        </Link>

        <Link to="/admin/flagged" className="block transition hover:opacity-80">
          <Card>
            <CardTitle hint="Signup attempts that failed roster matching.">Flagged signups</CardTitle>
            <p className="text-3xl font-semibold tabular-nums">{counts?.openFlags ?? '—'}</p>
            <p className="text-sm text-ink-600">awaiting review</p>
          </Card>
        </Link>

        <Link to="/admin/outcomes" className="block transition hover:opacity-80">
          <Card>
            <CardTitle hint="Where students are headed after graduation, by school.">
              Career outcomes
            </CardTitle>
            <p className="text-3xl font-semibold tabular-nums">{onboarded ?? '—'}</p>
            <p className="text-sm text-ink-600">students have completed onboarding</p>
          </Card>
        </Link>
      </div>
    </>
  )
}
