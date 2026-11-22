import { request } from './api'
import type { Job, Match } from './jobs'

export const statuses = {
  wishlist: '待投递', applied: '已投递', written_test: '笔试中', interview_1: '一面',
  interview_2: '二面', hr_interview: 'HR 面', offer: 'Offer', rejected: '已拒绝', withdrawn: '已放弃',
} as const
export type Status = keyof typeof statuses
export type PipelineData = { target: string | null; columns: Record<Status, Application[]>; upcoming: Schedule[];
  has_more?: Record<Status, boolean>; counts?: Partial<Record<Status, number>>; next_actions?: Application[] }
export type Metadata = {
  industry?: string | null; education?: string | null; major?: string | null; experience?: string | null
  skills?: string[]; duties?: string | null; requirements_text?: string | null
  source?: string | null; published_at?: string | null; source_status?: string
}
export type Position = Job & {
  job_description: string; favorite: boolean; archived: boolean; discovery_metadata: Metadata | null
}
export type ResumeBlock = { number: number; text: string; optimization_id?: number | null }
export type ResumeVersion = {
  id: number; content_id: number | null; version_name: string; version_number: number
  previous_id: number | null; target_job_id: number | null; target_position: string | null
  change_summary: string; content?: ResumeBlock[]
}
export type ResumePreview = {
  blocks: ResumeBlock[]; optimizations: (ResumeBlock & { id: number; reason: string })[]
  recommendations: Match['recommendations']; gaps: string[]
}
export type Application = {
  id: number; job_id: number; resume_version_id: number | null; revision: number; channel: string | null
  applied_at: string | null; updated_at: string; valid_submission: boolean; current_status: Status
  notes?: string; next_action?: string; contact?: string; feedback?: string; rejection_reason?: string
  job: { company: string | null; position: string; jd?: string; source_url?: string }
}
export type StatusEvent = { id: number; previous_status: Status | null; new_status: Status; changed_at: string; notes: string | null }
export type CareerContext = { application_id: number; job_id: number; role: string; match_id: number | null;
  projects: { id: number; session_id: number; name: string; selected: boolean }[] }
export type Schedule = {
  id: number; application_id: number; company: string | null; position: string; revision: number
  timezone: string; scheduled_at: string; ends_at: string; duration: number; interview_round: string
  interview_type: string; location_or_url: string | null; preparation_notes: string | null
  result: string; retrospective: string | null
}
export type Metric = { numerator: number; denominator: number; rate: number | null }
export type Counts = {
  submitted: number; valid: number; invited: number; offer: number; resume_passed: number
  written_test: number; written_passed: number; interview_decided: number; interview_passed: number
  rates: Record<string, Metric>
}
export type Period = { start?: string; end?: string }
export type Analytics = {
  start: string; end: string; summary: Counts; minimum_sample: number; sample_insufficient: boolean
  by_position: (Counts & { label: string })[]; by_resume: (Counts & { id: number | null; label: string })[]
  trend: { date: string; count: number }[]
}
export type Strategy = {
  id: number; state: string; statistics: Analytics; error_code: string | null; created_at: string
  analysis: { current_state: string; observations: string[]; inferences: string[]
    hypotheses: string[]; priority_actions: string[]; next_goal: string } | null
}

function json(method: string, body: unknown): RequestInit {
  return { method, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) }
}

export const applications = {
  positions: (filters = '') => request<Position[]>(`/jobs?${filters}`),
  position: (id: number) => request<Position>(`/jobs/${id}`),
  capture: (body: unknown) => request<Position>('/jobs/import-jd', json('POST', body)),
  updatePosition: (id: number, body: unknown) => request<Position>(`/jobs/${id}`, json('PATCH', body)),
  archive: (id: number) => request<void>(`/jobs/${id}`, { method: 'DELETE' }),
  match: (id: number) => request<Match>(`/jobs/${id}/match`),
  versions: () => request<ResumeVersion[]>('/resume-versions'),
  version: (id: number) => request<ResumeVersion>(`/resume-versions/${id}`),
  versionPreview: (body: unknown) => request<ResumePreview>('/resume-versions/preview', json('POST', body)),
  saveVersion: (body: unknown, id?: number) => id
    ? request<ResumeVersion>(`/resume-versions/${id}`, json('PATCH', body))
    : request<ResumeVersion>('/resume-versions', json('POST', body)),
  detail: (id: number) => request<Application>(`/applications/${id}`),
  careerContext: (id: number) => request<CareerContext>(`/applications/${id}/career-context`),
  create: (body: unknown) => request<Application>('/applications', json('POST', body)),
  edit: (id: number, body: unknown) => request<Application>(`/applications/${id}`, json('PATCH', body)),
  move: (record: Application, status: Status, notes?: string) => request<Application>(`/applications/${record.id}/status`,
    json('POST', { revision: record.revision, request_id: crypto.randomUUID(), status, notes })),
  history: (id: number) => request<StatusEvent[]>(`/applications/${id}/history`),
  pipeline: (limit?: number) => request<PipelineData>(limit ? `/job-pipeline?limit_per_status=${limit}` : '/job-pipeline'),
  boardPage: (status: Status, previous: Application, limit: number) => request<Application[]>('/applications?' +
    new URLSearchParams({ status, limit: String(limit), recent: 'true', before_time: previous.updated_at, before_id: String(previous.id) })),
  schedules: () => request<Schedule[]>('/interview-schedules'),
  saveSchedule: (body: unknown, id?: number) => id
    ? request<Schedule>(`/interview-schedules/${id}`, json('PATCH', body))
    : request<Schedule>('/interview-schedules', json('POST', body)),
  analytics: (period: Period) => request<Analytics>(`/job-analytics?${new URLSearchParams(period)}`),
  strategyPreview: (body: Period) => request<{ host: string; approval: string; payload: unknown }>(
    '/job-strategy/preview', json('POST', body)),
  analyze: (body: Period & { approval: string }) => request<Strategy>('/job-strategy/analyze', json('POST', body)),
  report: (id: number) => request<Strategy>(`/job-strategy/reports/${id}`),
  reports: () => request<Strategy[]>('/job-strategy/reports'),
}

export function field(data: FormData, key: string) {
  return String(data.get(key) ?? '').trim() || null
}
