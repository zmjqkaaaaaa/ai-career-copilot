import { request } from './api'

export type Account = {
  id: number
  email: string
  username: string
  is_active: boolean
  created_at: string
  updated_at: string
}

export const authApi = {
  register: (email: string, username: string, password: string) => request<Account>('/auth/register', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, username, password }),
  }, false),
  login: (email: string, password: string) => request<Account>('/auth/session', {
    method: 'POST', body: new URLSearchParams({ username: email, password }),
  }, false),
  logout: () => request<void>('/auth/session', { method: 'DELETE' }),
  deleteAccount: (password: string) => request<{ status: 'deleted' }>('/users/me', {
    method: 'DELETE', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ password, confirmed: true }),
  }),
  me: (signal: AbortSignal) => request<Account>('/users/me', { signal }, false),
}
