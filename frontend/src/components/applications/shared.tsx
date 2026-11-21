import type { ReactNode } from 'react'
import { errorMessage } from '../../services/api'
import type { Application, Schedule } from '../../services/applications'

export type Run = (action: () => Promise<void>, reload?: boolean) => Promise<void>

export function Panel({ title, children }: { title: string; children: ReactNode }) {
  return <section className="surface detail-panel application-panel"><h2>{title}</h2>{children}</section>
}

export function JobName({ row }: { row: Application }) {
  return <>{row.job.company || '公司未知'} · {row.job.position}</>
}

export function dateLabel(value: string | null) {
  return value ? new Date(value).toLocaleString('zh-CN') : '—'
}

export function appointmentTime(row: Schedule) {
  return new Intl.DateTimeFormat('zh-CN', {
    dateStyle: 'medium', timeStyle: 'short', timeZone: row.timezone,
  }).format(new Date(row.scheduled_at))
}

export function showFailure(error: unknown, sink: (message: string) => void) {
  sink(errorMessage(error))
}
