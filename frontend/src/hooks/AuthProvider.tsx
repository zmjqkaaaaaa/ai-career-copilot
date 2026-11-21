import { createContext, useContext, useEffect, useState } from 'react'
import type { ReactNode } from 'react'
import { ApiError, errorMessage } from '../services/api'
import { authApi } from '../services/auth'
import type { Account } from '../services/auth'
import { profileApi } from '../services/profile'
import type { Profile, ProfileInput } from '../services/profile'

type ProfileState =
  | { state: 'loading' | 'missing' }
  | { state: 'error'; message: string }
  | { state: 'ready'; data: Profile }

type AuthContextValue = {
  account: Account | null
  checking: boolean
  authError: string | null
  profile: ProfileState
  reloadProfile: () => void
  retrySession: () => void
  login: (email: string, password: string) => Promise<void>
  logout: () => Promise<void>
  saveProfile: (input: ProfileInput) => Promise<void>
}

const AuthContext = createContext<AuthContextValue | null>(null)
const loadingProfile: ProfileState = { state: 'loading' }

export function AuthProvider({ children }: { children: ReactNode }) {
  const [account, setAccount] = useState<Account | null>(null)
  const [checking, setChecking] = useState(true)
  const [authError, setAuthError] = useState<string | null>(null)
  const [sessionCheck, setSessionCheck] = useState(0)
  const [profileState, setProfileState] = useState<{ userId: number; value: ProfileState } | null>(null)
  const [profileCheck, setProfileCheck] = useState(0)
  const userId = account?.id
  const profile = profileState && profileState.userId === userId ? profileState.value : loadingProfile

  useEffect(() => {
    const controller = new AbortController()
    authApi.me(controller.signal)
      .then((user) => { if (!controller.signal.aborted) setAccount(user) })
      .catch((error: unknown) => {
        if (!controller.signal.aborted && !(error instanceof ApiError && error.status === 401)) {
          setAuthError(errorMessage(error))
        }
      })
      .finally(() => { if (!controller.signal.aborted) setChecking(false) })
    return () => controller.abort()
  }, [sessionCheck])

  useEffect(() => {
    function expireSession() {
      setAccount(null)
      setProfileState(null)
    }
    window.addEventListener('career:session-expired', expireSession)
    return () => window.removeEventListener('career:session-expired', expireSession)
  }, [])

  useEffect(() => {
    if (userId === undefined) return
    const controller = new AbortController()
    profileApi.me(controller.signal).then((data) => {
      if (!controller.signal.aborted) setProfileState({ userId, value: { state: 'ready', data } })
    }).catch((error: unknown) => {
      if (controller.signal.aborted || (error instanceof ApiError && error.status === 401)) return
      const value: ProfileState = error instanceof ApiError && error.code === 'PROFILE_NOT_FOUND'
        ? { state: 'missing' }
        : { state: 'error', message: errorMessage(error) }
      setProfileState({ userId, value })
    })
    return () => controller.abort()
  }, [userId, profileCheck])

  const context: AuthContextValue = {
    account, checking, authError, profile,
    reloadProfile: () => { setProfileState(null); setProfileCheck((value) => value + 1) },
    retrySession: () => { setAuthError(null); setChecking(true); setSessionCheck((value) => value + 1) },
    async login(email, password) {
      const user = await authApi.login(email, password)
      setAuthError(null)
      setAccount(user)
    },
    async logout() {
      await authApi.logout()
      setAccount(null)
      setProfileState(null)
    },
    async saveProfile(input) {
      if (userId === undefined) throw new Error('Authentication required')
      const data = await profileApi.save(input)
      setProfileState((current) => current?.userId === userId
        ? { userId, value: { state: 'ready', data } } : current)
    },
  }

  return <AuthContext.Provider value={context}>{children}</AuthContext.Provider>
}

export function useAuth() {
  const auth = useContext(AuthContext)
  if (!auth) throw new Error('AuthProvider is missing')
  return auth
}
