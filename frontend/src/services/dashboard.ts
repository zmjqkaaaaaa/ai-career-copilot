import { request } from './api'
import type { Status } from './applications'

export type Dashboard = {
  day: string
  target_position: string | null
  profile_complete: boolean
  skills: { verified: number; self_reported: number; inferred: number; unknown: number }
  match: { id: number; job_id: number; position: string; gaps: { name: string; status: string }[] } | null
  projects: { id: number; session_id: number; name: string; selected: boolean }[]
  tasks: { id: number; title: string; minutes: number; status: string }[]
  interview: { session_id: number; target: string; score: number | null; answered: number; weakness: string | null } | null
  applications: Partial<Record<Status, number>>
  next_action: {
    kind: 'application' | 'learning' | 'interview' | 'matching' | 'profile' | 'exploration'
    text: string
    application_id: number | null
  }
}

export function loadDashboard(signal: AbortSignal) {
  const day = new Intl.DateTimeFormat('sv-SE').format(new Date())
  return request<Dashboard>(`/dashboard?day=${day}`, { signal })
}
