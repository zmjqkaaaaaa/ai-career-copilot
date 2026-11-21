import { request } from './api'

export type Setup = { mode: string; difficulty: string; style: string; minutes: number; deep_followup: boolean;
  teaching: boolean; target?: string; resume_content_id?: number; job_id?: number; recommendation_id?: number;
  repository_id?: number; commit?: string; interview_schedule_id?: number; stage_minutes?: Record<string, number> }
type Option = { id: number; label: string; version?: number }
export type Options = { target: string; modes: Record<string,string>; styles: Record<string,string>;
  difficulties: Record<string,string>; stages: Record<string,string>; resumes: Option[]; jobs: Option[]; projects: Option[];
  repositories: (Option & { active_commit: string; versions: string[] })[] }
type Schedule = { stage: string; questions: number; minutes: number | null }
type Sources = Record<string, string | number | boolean | Record<string,string | number | boolean>>
export type Preparation = { target: string; sources: Sources; schedule: Schedule[]; source_types: string[]; has_project_code: boolean }
export type Reference = { id: string; kind: string; text?: string; path?: string; start?: number; end?: number; symbol?: string; commit?: string }
type Question = { id: number; ordinal: number; stage: string; parent_id: number | null; question: string;
  knowledge_point: string; basis: string; hint: string | null; references: Reference[] }
type Task = { id: number; kind: string; state: string; attempt: number; error_code: string | null }
export type Session = { id: number; target: string; settings: Setup; state: string; created_at: string;
  deadline: string | null; finish_reason: string | null; score?: number | null; sources: Sources }
export type Detail = Session & { question: Question | null; questions: { id: number; ordinal: number; stage: string;
  question: string; answered: boolean; followup: boolean }[]; task: Task | null; schedule: Schedule[]; answered: number;
  planned: number; remaining: number; time_expired: boolean; assessed: string[]; unassessed_stages: string[] }
export type Turn = { kind: 'start' | 'answer'; question_id?: number; answer?: string }
export type Preview = { approval: string; context: unknown; model_host: string }
type Rated = { score: number | null; coverage: number | null; answered: number }
type Topic = { question_id: number; knowledge_point: string; feedback: string[]; knowledge?: string; exercise?: string; acceptance?: string }
export type Report = Rated & { id: number; target: string; mode: string; duration_seconds: number; finish_reason: string;
  rubric_version: string; stages: Record<string,Rated>; dimensions: { type: string; key: string; label: string; score: number | null; evidence_count: number }[];
  strengths: Topic[]; weaknesses: Topic[]; unassessed_stages: string[]; contributions: string[]; practice_evidence: string[];
  sources: Sources;
  turns: { question_id: number; question: string; knowledge_point: string; answer: string; score: number | null; coverage: number;
    corrected_idea: string; answer_outline: string[]; references: Reference[]; ratings: { key: string; label: string;
    score: number | null; quote: string | null; reason: string }[] }[] }
export type Training = { tasks: { id: number; session_id: number; state: string; due_at: string; title: string;
  priority: string; description: string; acceptance: string; review_question: string; next_goal: string }[]; total: number; done: number }

const base = '/interviews'
const route = (id: number, tail = '') => `${base}/sessions/${id}${tail}`
const json = (method: string, value?: unknown): RequestInit => ({
  method, ...(value === undefined ? {} : { headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(value) }),
})

export const interview = {
  options: () => request<Options>(`${base}/options`),
  prepare: (value: Setup) => request<Preparation>(`${base}/prepare`, json('POST', value)),
  create: (value: Setup, nonce: string) => request<Session>(`${base}/sessions`, json('POST', { ...value, request_id: nonce })),
  history: (before?: number) => request<Session[]>(`${base}/sessions${before ? '?before=' + before : ''}`),
  detail: (id: number) => request<Detail>(route(id)),
  preview: (id: number, turn: Turn) => request<Preview>(route(id, '/preview'), json('POST', turn)),
  send: (id: number, turn: Turn, approval: string) =>
    request<Task>(route(id, turn.kind === 'start' ? '/start' : '/answers'), json('POST', { ...turn, approval })),
  retry: (id: number, task: number) => request<Task>(route(id, `/tasks/${task}/retry`), json('POST')),
  finish: (id: number) => request<Report>(route(id, '/finish'), json('POST')),
  report: (id: number) => request<Report>(route(id, '/report')),
  training: () => request<Training>(`${base}/training-plans`),
  changeTask: (id: number, state: string) => request<unknown>(`${base}/training-tasks/${id}`, json('PATCH', { state })),
}
