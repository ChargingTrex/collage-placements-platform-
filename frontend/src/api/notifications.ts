import { api } from '@/api/client'
import { rowsOf } from '@/api/opportunities'
import type { Paginated } from '@/api/roster'

export type NotificationKind = 'new_opportunity' | 'deadline_soon'

export interface AppNotification {
  id: string
  kind: NotificationKind
  opportunity: { id: string; title: string }
  created_at: string
  read_at: string | null
}

/** Tells the nav badge to refetch after the list changes. */
export const NOTIFICATIONS_CHANGED = 'pcp:notifications-changed'

export const notificationsApi = {
  list: async (unreadOnly = false) =>
    rowsOf(
      await api.get<Paginated<AppNotification> | AppNotification[]>(
        `/api/notifications/${unreadOnly ? '?unread=true' : ''}`,
      ),
    ),
  markRead: (id: string) => api.post<void>(`/api/notifications/${id}/read`),
  markAllRead: () => api.post<void>('/api/notifications/read-all'),
}

export function notificationText(n: AppNotification): string {
  return n.kind === 'deadline_soon'
    ? `Deadline coming up: ${n.opportunity.title}`
    : `New opportunity open to you: ${n.opportunity.title}`
}
