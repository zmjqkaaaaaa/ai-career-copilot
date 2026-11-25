import { ApiError, request } from './api'

export type Resume = {
  id: number; original_filename: string; file_type: 'pdf' | 'docx'; file_size: number
  parse_status: string; parse_error: string | null; created_at: string
}
export type Block = { number: number; location: string; text: string; section?: keyof typeof factGroups | null }
export type Anchor = { block_number: number; quote: string }
export type Fact = { original: string; normalized: string | null; source: Anchor | null; status: 'extracted' | 'uncertain' | 'user_confirmed' }
export const factGroups = {
  education: '教育背景', internships: '实习经历', projects: '项目经历', skills: '技能',
  certificates: '证书', competitions: '竞赛', languages: '语言', other_experiences: '工作及其他经历',
} as const
export type Facts = Record<keyof typeof factGroups, Fact[]>
export type Content = {
  id: number; version: number; confirmed: boolean; blocks: Block[]
  structured_data: Facts | null; model_blocks: Block[] | null
  metadata_json: { model?: string; prompt_version?: string; rejected: number; method?: 'local_sections' } | null
}
export type Job = {
  id: number; kind: 'parse' | 'extract' | 'analyze' | 'optimize'
  state: 'queued' | 'running' | 'succeeded' | 'failed'; attempt: number
  result_id: number | null; error_code: string | null
  scheduled_at: string; started_at: string | null; finished_at: string | null; worker_available?: boolean | null
}
export type EvidenceStatus = 'verified' | 'self_reported' | 'inferred' | 'unknown'
export type Point = { title: string; reason: string; sources: Anchor[] }
export type Skill = { name: string; category: string; level: string; status: EvidenceStatus; reason: string; sources: Anchor[] }
export type Analysis = { id: number; resume_id: number; content_id: number; target_direction: string; model_name: string; prompt_version: string; created_at: string }
export type CareerReport = {
  analysis: Analysis
  report: {
    summary: Point; education: Point[]; project_practice: Point[]; strengths: Point[]
    gaps: Point[]; directions: Point[]; recommended_projects: Point[]; next_steps: Point[]; skills: Skill[]
  }
}
export type Optimization = {
  id: number; section: string; original_content: string; optimized_content: string; optimization_reason: string
  interview_question: string; needs_evidence: boolean; block_number: number; confirmed_text: string | null
}

function json(method: string, body: unknown): RequestInit {
  return { method, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) }
}

async function optional<T>(promise: Promise<T>): Promise<T | null> {
  try { return await promise }
  catch (error) {
    if (error instanceof ApiError && error.status === 404) return null
    throw error
  }
}

export const careerApi = {
  provider: (signal: AbortSignal) => request<{ host: string | null; model: string | null }>('/career/provider', { signal }),
  list: (signal: AbortSignal) => request<Resume[]>('/resumes', { signal }),
  upload(file: File) {
    const body = new FormData()
    body.set('file', file)
    return request<Resume>('/resumes/upload', { method: 'POST', body })
  },
  delete: (id: number) => request<void>(`/resumes/${id}`, { method: 'DELETE' }),
  read: (id: number, signal: AbortSignal) => request<Resume>(`/resumes/${id}`, { signal }),
  content: (id: number, signal: AbortSignal, contentId?: number | null) => optional(request<Content>(
    `/resumes/${id}/content${contentId ? `?content_id=${contentId}` : ''}`, { signal },
  )),
  preview: (id: number, content: number, signal: AbortSignal) => request<Block[]>(`/resumes/${id}/preview?content_id=${content}`, { signal }),
  parse: (id: number, reparse: boolean, retry: boolean) => request<Job>(`/resumes/${id}/parse`, json('POST', { reparse, retry })),
  extract: (id: number, content: number, hidden: number[], retry: boolean, host: string) => request<Job>(`/resumes/${id}/extract`, json('POST', { content_id: content, hidden_blocks: hidden, retry, provider_host: host, accept_external_processing: true })),
  update: (id: number, content: number, structured_data: Facts) => request<Content>(`/resumes/${id}/content`, json('PUT', { content_id: content, structured_data })),
  localDraft: (id: number, content: number, hidden: number[]) => request<Content>(`/resumes/${id}/local-draft`, json('POST', { content_id: content, hidden_blocks: hidden })),
  analyze: (id: number, content: number, target: string, retry: boolean, host: string) => request<Job>('/career/analyze', json('POST', { resume_id: id, content_id: content, target_direction: target, retry, provider_host: host, accept_external_processing: true })),
  analyses: (id: number, signal: AbortSignal) => request<Analysis[]>(`/career/analyses?resume_id=${id}`, { signal }),
  profile: (id: number, signal: AbortSignal) => request<CareerReport>(`/career/profile?analysis_id=${id}`, { signal }),
  optimize: (id: number, content: number, target: string, retry: boolean, host: string) => request<Job>(`/resumes/${id}/optimize`, json('POST', { content_id: content, target_direction: target, retry, provider_host: host, accept_external_processing: true })),
  optimizations: (id: number, signal: AbortSignal) => request<Optimization[]>(`/resumes/${id}/optimizations`, { signal }),
  confirm: (id: number, record: number, text: string) => request<Optimization>(`/resumes/${id}/optimizations/${record}/confirm`, json('POST', { text })),
  jobs: (id: number, signal: AbortSignal) => request<Job[]>(`/resumes/${id}/jobs`, { signal }),
  job: (id: number, signal: AbortSignal) => request<Job>(`/resume-jobs/${id}`, { signal }),
}
