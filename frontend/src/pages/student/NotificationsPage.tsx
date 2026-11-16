import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'

import { ApiError } from '@/api/client'
import {
  NOTIFICATIONS_CHANGED,
  notificationsApi,
  notificationText,
  type AppNotification,
} from '@/api/notifications'
import { Alert, Badge, Button, Card, EmptyState, PageHeader } from '@/components/ui'

export default function NotificationsPage() {
  const [rows, setRows] = useState<AppNotification[] | null>(null)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    try {
      setRows(await notificationsApi.list())
      setError(null)
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : 'Could not load notifications.')
    }
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  async function change(run: () => Promise<unknown>) {
    try {
      await run()
      await load()
      window.dispatchEvent(new Event(NOTIFICATIONS_CHANGED))
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : 'That did not work.')
    }
  }

  const unread = rows?.filter((row) => !row.read_at).length ?? 0

  return (
    <>
      <PageHeader title="Notifications" subtitle={unread ? `${unread} unread` : 'You are up to date.'} />
      {error ? <div className="mb-4"><Alert tone="error">{error}</Alert></div> : null}
      <div className="mb-4 flex justify-end">
        <Button
          variant="secondary"
          disabled={unread === 0}
          onClick={() => void change(() => notificationsApi.markAllRead())}
        >
          Mark all read
        </Button>
      </div>
      {rows === null && !error ? (
        <p className="py-8 text-center text-sm text-ink-400">Loading…</p>
      ) : rows && rows.length === 0 ? (
        <EmptyState title="No notifications" />
      ) : (
        <ul className="space-y-2">
          {rows?.map((row) => (
            <li key={row.id}>
              <Card className="flex flex-wrap items-center justify-between gap-3 !p-4">
                <div>
                  <p className="text-sm">
                    {!row.read_at ? <Badge tone="brand">New</Badge> : null} {notificationText(row)}
                  </p>
                  <p className="text-xs text-ink-400">
                    {new Date(row.created_at).toLocaleDateString('en-IN')} ·{' '}
                    <Link to="/student/jobs" className="underline">
                      See jobs
                    </Link>
                  </p>
                </div>
                {!row.read_at ? (
                  <Button size="sm" variant="ghost" onClick={() => void change(() => notificationsApi.markRead(row.id))}>
                    Mark read
                  </Button>
                ) : null}
              </Card>
            </li>
          ))}
        </ul>
      )}
    </>
  )
}
