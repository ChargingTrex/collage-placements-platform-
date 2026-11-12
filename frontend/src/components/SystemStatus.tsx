import { useEffect, useState } from 'react'

import { fetchHealth, type Health } from '@/api/health'

type State =
  | { phase: 'loading' }
  | { phase: 'ready'; health: Health }
  | { phase: 'error'; message: string }

const DOT: Record<string, string> = {
  ok: 'bg-ok-600',
  degraded: 'bg-warn-600',
  down: 'bg-bad-600',
}

/**
 * Phase 0 proof-of-wiring: the React app reaching the Django API.
 * Stays useful afterwards as an at-a-glance backend status panel.
 */
export default function SystemStatus() {
  const [state, setState] = useState<State>({ phase: 'loading' })

  useEffect(() => {
    let cancelled = false
    fetchHealth()
      .then((health) => !cancelled && setState({ phase: 'ready', health }))
      .catch((error: Error) => !cancelled && setState({ phase: 'error', message: error.message }))
    return () => {
      cancelled = true
    }
  }, [])

  if (state.phase === 'loading') {
    return <p className="text-sm text-ink-400">Checking backend…</p>
  }

  if (state.phase === 'error') {
    return (
      <div className="rounded-lg border border-bad-600/30 bg-bad-50 p-4">
        <p className="flex items-center gap-2 text-sm font-medium text-bad-600">
          <span className={`size-2 rounded-full ${DOT.down}`} aria-hidden />
          Backend unreachable
        </p>
        <p className="mt-1 text-sm text-ink-600">{state.message}</p>
        <p className="mt-2 text-xs text-ink-400">
          Start it with <code className="rounded bg-ink-100 px-1">python manage.py runserver</code>.
        </p>
      </div>
    )
  }

  const { health } = state
  const rows = [
    { label: 'Database', check: health.checks.database, note: health.checks.database.engine },
    { label: 'File storage', check: health.checks.storage, note: health.checks.storage.backend },
    {
      label: 'Matching engine',
      check: health.checks.matching_engine,
      note: health.checks.matching_engine.detail,
    },
  ]

  return (
    <div className="rounded-lg border border-ink-200 bg-white p-4">
      <p className="flex items-center gap-2 text-sm font-medium">
        <span className={`size-2 rounded-full ${DOT[health.status] ?? DOT.down}`} aria-hidden />
        Backend {health.status}
      </p>
      <dl className="mt-3 space-y-2">
        {rows.map(({ label, check, note }) => (
          <div key={label} className="flex items-baseline justify-between gap-4 text-sm">
            <dt className="text-ink-600">{label}</dt>
            <dd className="text-right">
              <span className={check.ok ? 'text-ok-600' : 'text-bad-600'}>
                {check.ok ? 'ok' : 'failing'}
              </span>
              {note ? <span className="ml-2 text-xs text-ink-400">{String(note)}</span> : null}
            </dd>
          </div>
        ))}
      </dl>
    </div>
  )
}
