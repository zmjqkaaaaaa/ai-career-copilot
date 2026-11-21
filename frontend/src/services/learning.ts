import { request } from './api'

export type Topic = { id: string; category: string; title: string; requires: string[]; exercise: string; acceptance: string; type: string; minutes: number }
export type Catalog = { topics: Topic[]; categories: Record<string,string>; modes: Record<string,string> }
type Evidence = { source: string; ref: number; text: string; status: string }
export type Diagnosis = { target: string; suggested_minutes: number | null; categories: Record<string,string>; summary: Record<string,number>; topics: {
  topic: string; title: string; category: string; status: string; confidence: string; level: number | null;
  last_verified_at: string | null; priority: number; evidence: Evidence[] }[] }
export type Lesson = { explanation?: string; example?: string; question?: string; next_step?: string; summary?: string; text?: string }
export type Path = { id: number; version: number; data: { target: string; goal: string; reason: string; weekly_minutes: number;
  estimated_weeks: number; modules: (Topic & { reason: string })[]; verified: string[]; mentor?: Lesson } }
export type Task = { id: number; status: string; actual_minutes: number; topic: string; due: string; data: Topic & { checkpoint?: string } }
export type Session = { id: number; topic: string; mode: string; summary: Lesson }
export type Message = { id: number; role: string; data: Lesson }
export type Resource = { id: number | null; topic: string; title: string; kind: string; url?: string; text?: string; source: string; credibility: string }
export type Evaluation = { status: string; score: number | null; coverage: number; revision: string; next_step: string;
  fixture?: { case: string; expected: number; observed: number | null; passed: boolean }[] | null;
  static: { detail: string }; correct: string[]; errors: string[]; missing: string[];
  ratings: { criterion: string; level: number | null; quote: string | null; reason: string }[] }
export type Assignment = Topic & { submission: string; rubrics: Record<string,string[]>; fixtures: Record<string,string> }
export type Submission = { id: number; version: number; status: string; data: { kind: string; content: string; repository_url?: string }; evaluation?: Evaluation }
export type Assessment = { id: number; topic: string; form: number; questions: { id: string; question: string; choices: string[] }[];
  application: { type: string; question: string; acceptance: string };
  result: { score: number; mode: string; checked: { id: string; correct: boolean; answer: string }[] } | null }
export type Progress = { diagnosis: Diagnosis; completed: number; total: number; minutes: number; completion_rate: number;
  submissions: number; assessments: Assessment[]; history: { id: number; topic: string; created_at: string;
    data: { prior: string; status: string; score: number; reason: string } }[] }
export type Job = { id: number; state: string; attempt: number; error: string | null }
export type AIAction = { kind: 'lesson' | 'path' | 'evaluation'; record_id: number; message?: string }
export type Preview = { approval: string; payload: unknown; model_host: string }

const base = '/learning'
function send<T>(path: string, body: unknown, method = 'POST') {
  return request<T>(base + path, { method, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })
}
export const learning = {
  catalog: () => request<Catalog>(base + '/catalog'),
  diagnosis: () => request<Diagnosis>(base + '/diagnosis'),
  progress: () => request<Progress>(base + '/progress'),
  paths: () => request<Path[]>(base + '/paths'),
  path: (weekly_minutes: number, goal: string, id?: number) =>
    send<Path>(id ? '/paths/' + id : '/paths/generate', { weekly_minutes, goal }, id ? 'PATCH' : 'POST'),
  daily: (day: string) => request<{ tasks: Task[]; date: string; minutes: number }>(base + '/tasks/daily?day=' + day),
  addTask: (topic: string, minutes: number, day: string) => send<Task>('/tasks?day=' + day, { topic, minutes }),
  task: (id: number, status: string, actual_minutes: number) => send<Task>('/tasks/' + id, { status, actual_minutes }, 'PATCH'),
  sessions: () => request<Session[]>(base + '/sessions'),
  createSession: (topic: string, mode: string) => send<Session>('/sessions', { topic, mode }),
  messages: (session: number) => request<{ session: Session; messages: Message[] }>(base + '/sessions/' + session + '/history'),
  resources: (topic: string) => request<Resource[]>(base + '/resources?topic=' + encodeURIComponent(topic)),
  resource: (body: unknown) => send<Resource>('/resources', body),
  upload: (path: string, form: FormData) => request<unknown>(base + path, { method: 'POST', body: form }),
  assignments: () => request<Assignment[]>(base + '/assignments'),
  submissions: (topic: string) => request<Submission[]>(base + '/assignments/' + topic + '/submissions'),
  submit: (topic: string, body: unknown) => send<Submission>('/assignments/' + topic + '/submit', body),
  exam: (topic: string) => send<Assessment>('/assessments/start', { topic }),
  finishExam: (id: number, answers: Record<string,string>) => send<Assessment>('/assessments/' + id + '/submit', { answers }),
  jobs: () => request<Job[]>(base + '/jobs'),
  retry: (id: number) => send<Job>('/jobs/' + id + '/retry', {}),
  preview: (body: AIAction) => send<Preview>('/preview', body),
  approve: (body: AIAction, approval: string) => {
    const id = body.record_id
    const paths = { lesson: '/sessions/' + id + '/messages', evaluation: '/submissions/' + id + '/evaluate', path: '/paths/' + id + '/coach' }
    return send<Job>(paths[body.kind], { ...body, approval })
  },
}

