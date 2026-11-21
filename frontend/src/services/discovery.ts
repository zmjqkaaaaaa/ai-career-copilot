import { request } from './api'

export type Mode = 'guided' | 'assisted'
export type Step = 'turn' | 'pain' | 'research' | 'opportunity' | 'recommend' | 'prd'
export type Session = { id: number; title: string; mode: Mode; direction: string | null; weekly_hours: number | null }
export type Task = { id: number; kind: Step; state: 'queued' | 'running' | 'succeeded' | 'failed'; attempt: number; result_id: number | null; error_code: string | null }
export type Interest = { name: string; category: string; origin: string; reason: string; confidence: string }
export type Evidence = { kind: string; detail: string; message_id?: number | null }
export type Pain = { pain_point_name: string; target_user: string; scenario: string; user_problem: string; current_solution: string | null
  frequency: string | null; severity: string | null; validation_status: string; confidence: string; evidence: Evidence[]
  interview_target: string | null; interview_questions: string[]; demand_signal: string | null }
export type RecordData<T> = { id: number; data: T; created_at: string }
export type PainRecord = RecordData<Pain> & { revision: number }
export type Source = { id: number; title: string; url: string; excerpt: string; source_type: string; collected_at: string; method: string }
export type Claim = { text: string; sources: number[]; evidence_excerpt?: string | null }
export type Research = RecordData<{ topic: string; status: string; sources: Source[]; findings: Claim[] }> & { pain_point_id: number }
export type Competitor = { product_name: string; official_source: number | null } & Partial<Record<'positioning' | 'target_users' | 'features' | 'scenarios' | 'experience' | 'technology' | 'business_model' | 'advantages' | 'limitations' | 'differentiation', Claim | null>>
export type ResearchDetail = Research & { competitors: RecordData<Competitor>[] }
export type Rating = { dimension: string; label: string; rating: number | null; reason: string; basis: string; weight: number; references: string[] }
export type Opportunity = RecordData<{ score: number | null; coverage: number; version: string; ratings: Rating[];
  risks: string[]; differentiation: string; feasibility: string; validation_plan: string; evidence: Record<string, unknown> }> & { pain_point_id: number; research_id: number | null }
export type Project = { name: string; direction: string; background: string; target_user: string; pain: string; positioning: string; features: string[];
  ai_use: string; stack: string[]; difficulty: string; estimated_hours: number; learning: string[]; role_alignment: string;
  differentiation: string; risks: string[]; reason: string; deliverable: string; budget_fit?: boolean | null; estimated_weeks?: number | null }
export type ProjectRecord = RecordData<Project> & { opportunity_id: number; batch_id: number; favorite: boolean; selected: boolean }
export type Prd = { id: number; version: number; title: string; content: string; origin: string }
export type JobInput = { kind: Step; reference_id?: number; research_id?: number; message?: string; queries?: string[];
  sources?: { title: string; url: string; excerpt: string; source_type: string }[]; regenerate?: boolean }
export type Preview = { approval: string; payload: Record<string, unknown>; model_host: string | null; search_host: string | null }
export type Detail = Session & { background: Record<string, unknown>; search_configured: boolean; messages: { id: number; role: string; content: string; details: { questions: string[]; learning_note: string } | null }[];
  interests: RecordData<Interest>[]; pain_points: PainRecord[]; research: Research[]; opportunities: Opportunity[]; projects: ProjectRecord[]; tasks: Task[] }

function json(method: string, body: unknown): RequestInit {
  return { method, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) }
}

export const discoveryApi = {
  list: () => request<Session[]>('/discovery/sessions'),
  get: (id: number) => request<Detail>(`/discovery/sessions/${id}`),
  create: (title: string) => request<Session>('/discovery/sessions', json('POST', { title })),
  session: (current: Session) => request<Session>(`/discovery/sessions/${current.id}`, json('PUT', {
    title: current.title, mode: current.mode, direction: current.direction, weekly_hours: current.weekly_hours,
  })),
  interest: (session: number, id: number, body: Interest) => request(`/discovery/sessions/${session}/interests/${id}`, json('PUT', body)),
  preview: (id: number, body: JobInput) => request<Preview>(`/discovery/sessions/${id}/preview`, json('POST', body)),
  send: (id: number, body: JobInput, approval: string) => {
    const paths: Record<Step, string> = {
      turn: `/discovery/sessions/${id}/messages`, pain: `/discovery/sessions/${id}/pain-points`, research: `/research/competitors?session_id=${id}`,
      opportunity: `/opportunities/evaluate?session_id=${id}`, recommend: `/projects/recommendations?session_id=${id}`,
      prd: `/projects/recommendations/${body.reference_id}/prd`,
    }
    return request<Task>(paths[body.kind], json('POST', { ...body, approval }))
  },
  pain: (pain: PainRecord) => request(`/pain-points/${pain.id}?revision=${pain.revision}`, json('PUT', pain.data)),
  research: (id: number) => request<ResearchDetail>(`/research/competitors/${id}`),
  competitor: (research: number, id: number, body: Competitor) => request(`/research/competitors/${research}/records/${id}`, json('PUT', body)),
  opportunity: (item: Opportunity, body: unknown) => request(`/opportunities/${item.id}`, json('PUT', body)),
  project: (id: number, body: { favorite?: boolean; selected?: boolean; project?: Project }) =>
    request(`/projects/recommendations/${id}`, json('PUT', body)),
  prds: (id: number) => request<Omit<Prd, 'content'>[]>(`/projects/recommendations/${id}/prds`),
  prd: (id: number) => request<Prd>(`/prds/${id}`),
  save: (item: Prd) => request<Prd>(`/prds/${item.id}`, json('PUT', { title: item.title, content: item.content, version: item.version })),
  retry: (id: number) => request<Task>(`/discovery/tasks/${id}/retry`, { method: 'POST' }),
}

export function downloadMarkdown(item: Prd) {
  const link = document.createElement('a')
  link.href = URL.createObjectURL(new Blob([item.content], { type: 'text/markdown;charset=utf-8' }))
  link.download = `prd-${item.id}-v${item.version}.md`
  link.click()
  window.setTimeout(() => URL.revokeObjectURL(link.href), 1000)
}
