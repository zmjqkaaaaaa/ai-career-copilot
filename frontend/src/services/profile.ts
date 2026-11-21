import { request } from './api'

export type Experience = { title: string; description: string }
export type ProfileInput = {
  real_name: string | null
  undergraduate_school: string | null
  undergraduate_major: string | null
  undergraduate_degree: string | null
  graduate_school: string | null
  graduate_major: string | null
  graduation_year: number | null
  target_position: string | null
  interested_industries: string[]
  skills: string[]
  internship_experience: Experience[]
  project_experience: Experience[]
}

export type Profile = ProfileInput & { id: number; created_at: string; updated_at: string }

export const profileApi = {
  me: (signal: AbortSignal) => request<Profile>('/profiles/me', { signal }),
  save: (profile: ProfileInput) => request<Profile>('/profiles/me', {
    method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(profile),
  }),
}
