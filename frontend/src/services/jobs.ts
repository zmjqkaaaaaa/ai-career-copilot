import { request } from './api'

export type Requirement = {
  name: string; category: string; kind: string; importance: string; quote: string
}
export type Task = { id: number; kind: string; match_id: number | null; state: string; error_code: string | null; worker_available?: boolean | null }
export type Job = {
  id: number; position_name: string; company_name: string | null; location: string | null
  job_type: string | null; salary_range: string | null; source_url: string | null
  created_at: string; revision: number; confirmed: boolean; latest_score?: number | null
  parsed: { duties: string[]; position_name: string | null; department: string | null; company_name: string | null; location: string | null; job_type: string | null } | null
  requirements: Requirement[]; tasks: Task[]
}
export type Row = Requirement & {
  ordinal: number; status: string; evidence_status: string; sources: { quote: string; block_number?: number; location?: string }[]
  interpretation?: string
  checks?: { name: string; sources: { quote: string; block_number: number }[] }[]
}
export type Gap = Row & { priority: string; why: string; action: string; practice: string; validation: string }
export type Match = {
  id: number; job_id: number; content_id: number; position_name?: string; created_at: string; revision: number
  overall_score: number | null; evidence_coverage: number | null; scoring_version: string
  resume?: ResumeSource | null
  score_details: {
    dimensions: Record<string, { weight: number; score: number | null; required: number; rated: number }>
    requirements: Row[]; hard_flags: Row[]; verdict: string
  }
  recommendations: { generation_method?: 'local_fallback'; rationale: string; resume_focus: string[]; interview_focus: string[]; projects: string[]; next_steps: string[] } | null
}
export type ResumeSource = { content_id: number; resume_id: number; version: number; original_filename: string }
export type Version = ResumeSource & { id: number }
export const resumeVersionPath = (source: ResumeSource) => `/career-profile?resume=${source.resume_id}&content=${source.content_id}`
export type Preview = { host: string | null; payload: Record<string, unknown> }

function json(method: string, body: unknown): RequestInit {
  return { method, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) }
}

export const jobsApi = {
  list: () => request<Job[]>('/jobs'),
  history: () => request<Match[]>('/job-matches'),
  matchDetail: (id: number) => request<Match>(`/job-matches/${id}`),
  versions: () => request<Version[]>('/jobs/candidate-versions'),
  detail: (id: number) => request<Job>(`/jobs/${id}`),
  create: (body: Record<string, string | null>) => request<Job>('/jobs', json('POST', body)),
  remove: (id: number) => request<void>(`/jobs/${id}`, { method: 'DELETE' }),
  importText: (file: File) => {
    const body = new FormData()
    body.set('file', file)
    return request<{ job_description: string }>('/jobs/import', { method: 'POST', body })
  },
  preview: (path: string) => request<Preview>(`${path}-preview`),
  submitModel: (path: string, host: string, retry: boolean) => request<Task>(path, json('POST', {
    provider_host: host, accept_external_processing: true, retry,
  })),
  confirm: (id: number, revision: number, requirements: Requirement[]) =>
    request<Job>(`/jobs/${id}/requirements`, json('PUT', { revision, requirements })),
  match: (id: number, body: { content_id: number; revision: number; assessments: Record<number, string> }) =>
    request<Match>(`/jobs/${id}/match`, json('POST', body)),
  gaps: (id: number) => request<Gap[]>(`/job-matches/${id}/gaps`),
  task: (id: number) => request<Task>(`/job-analysis-tasks/${id}`),
}
