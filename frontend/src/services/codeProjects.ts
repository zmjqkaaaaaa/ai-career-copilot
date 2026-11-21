import { request } from './api'

export type Project = { id: number; slug: string; url: string; active_commit: string | null; recommendation_id: number | null;
  metadata: { description?: string; default_branch?: string; language?: string; stargazers_count?: number; updated_at?: string } }
export type Phase = 'analyze' | 'explain' | 'chat' | 'quiz' | 'grade'
export type Study = { commit: string; kind: Phase; file_id?: number; symbol?: string; question?: string;
  dimension?: string; mode?: string; quiz_id?: number; answer?: string }
export type Task = { id: number; state: 'queued' | 'running' | 'failed' | 'succeeded'; kind: Phase | 'import' | 'load';
  attempt: number; result_id: number | null; error_code: string | null; error_message: string | null; retry_at: number | null }
export type Detail = Project & { versions: { sha: string; created_at: string }[]; tasks: Task[] }
export type Evidence = { id: number; file_id: number; path: string; start: number; end: number; symbol: string | null; code: string }
export type CodeFile = { id: number; path: string; kind: string; language: string; size: number; loaded: boolean;
  core: boolean; readable: boolean }
export type Symbol = { name: string; kind: 'class' | 'function'; start: number; end: number }
export type Content = CodeFile & { content: string | null; index: { status: string; symbols: Symbol[] } | null }
export type Lesson = { id?: number; overview: string; question?: string | null;
  sections: { title: string; explanation: string; status: string; references: number[] }[];
  missing: string[]; exercises: string[]; evidence: Evidence[] }
export type Architecture = {
  tech_stack: { name: string; category: string; path: string; line: number; status: string }[];
  modules: { path: string; module: string; kind: string; symbols: number }[];
  entries: { path: string; line: number; reason: string }[];
  imports: { from: string; to: string; line: number }[];
  calls: { file: string; caller: string; name: string; line: number }[];
  routes: { file: string; path: string; method: string; name: string; line: number }[];
  models: { path: string; name: string; line: number }[];
  files_read: number; files_indexed: number; analysis: Lesson | null }
export type Preview = { approval: string; payload: unknown; model_host: string }
export type Quiz = { id: number; question: string; concept: string; dimension: string; mode: string | null; evidence: Evidence[] }
export type Attempt = { id: number; quiz_id: number; dimension: string; answer: string; score: number; explanation: string;
  practice: string; expected_answer: string; criteria: { label: string; result: string; feedback: string }[] }
export type Mastery = { dimensions: { key: string; label: string; status: string; best_score: number | null; attempts: number;
  self_report: string | null; inferred: string | null; practice: string }[]; attempts: Attempt[] }

const root = '/code-projects'
const json = (method: string, body?: unknown): RequestInit => ({
  method, ...(body === undefined ? {} : { headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) }),
})
const versioned = (id: number, action: string, commit: string) => `${root}/${id}/${action}?commit=${commit}`

export const mentor = {
  list: () => request<Project[]>(root),
  create: (url: string, recommendation_id?: number) =>
    request<{ project: Project; task: Task }>(`${root}/import`, json('POST', { url, recommendation_id })),
  recommendation: (id: number) => request<{ id: number; name: string }>(`${root}/recommendations/${id}`),
  detail: (id: number) => request<Detail>(`${root}/${id}`),
  refresh: (id: number) => request<{ project: Project; task: Task }>(`${root}/${id}/refresh`, json('POST')),
  remove: (id: number) => request<void>(`${root}/${id}`, json('DELETE')),
  files: (id: number, commit: string) => request<CodeFile[]>(versioned(id, 'files', commit)),
  file: (id: number, commit: string, file: number) => request<Content>(versioned(id, `files/${file}`, commit)),
  load: (id: number, commit: string, file: number) =>
    request<{ task: Task | null }>(versioned(id, `files/${file}/load`, commit), json('POST')),
  architecture: (id: number, commit: string) => request<Architecture>(versioned(id, 'architecture', commit)),
  knowledge: (id: number, commit: string, query: string) =>
    request<{ matches: Evidence[] }>(versioned(id, 'knowledge', commit) + '&q=' + encodeURIComponent(query)),
  explanations: (id: number, commit: string) => request<Lesson[]>(versioned(id, 'explanations', commit)),
  history: (id: number, commit: string) => request<Lesson[]>(versioned(id, 'chat/history', commit)),
  quizzes: (id: number, commit: string) => request<Quiz[]>(versioned(id, 'quizzes', commit)),
  mastery: (id: number, commit: string) => request<Mastery>(versioned(id, 'mastery-report', commit)),
  selfReport: (id: number, commit: string, dimension: string, note: string) =>
    request<{ id: number }>(versioned(id, 'mastery-report/self-report', commit), json('PUT', { dimension, note })),
  preview: (id: number, body: Study) => request<Preview>(`${root}/${id}/preview`, json('POST', body)),
  send: (id: number, body: Study, approval: string) => {
    const actions = { analyze: 'analyze', explain: 'explain', chat: 'chat', quiz: 'quizzes/generate',
      grade: `quizzes/${body.quiz_id}/submit` }
    return request<Task>(`${root}/${id}/${actions[body.kind]}`, json('POST', { ...body, approval }))
  },
  retry: (id: number, task: number) => request<Task>(`${root}/${id}/tasks/${task}/retry`, json('POST')),
}
