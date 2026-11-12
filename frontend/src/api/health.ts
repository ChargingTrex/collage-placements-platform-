import { api } from '@/api/client'

export type HealthCheck = { ok: boolean } & Record<string, unknown>

export interface Health {
  status: 'ok' | 'degraded'
  service: string
  debug: boolean
  checks: {
    database: HealthCheck & { engine?: string }
    storage: HealthCheck & { backend?: string; location?: string }
    matching_engine: HealthCheck & { backend?: string; detail?: string }
  }
}

export const fetchHealth = () => api.get<Health>('/api/health', { auth: false })
