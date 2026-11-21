import { useState } from 'react'
import type { FormEvent } from 'react'
import { Link, Navigate, useLocation, useNavigate } from 'react-router'
import { useAuth } from '../hooks/AuthProvider'
import { routes } from '../routes'
import { errorMessage } from '../services/api'
import { authApi } from '../services/auth'

export function AuthPage({ mode }: { mode: 'login' | 'register' }) {
  const { account, checking, login } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()
  const [email, setEmail] = useState<string>(location.state?.email ?? '')
  const [pending, setPending] = useState(false)
  const [error, setError] = useState('')
  const registering = mode === 'register'
  const destination = location.state?.from
  const search = typeof location.state?.search === 'string' && location.state.search.startsWith('?') ? location.state.search : ''
  const returnPath = destination === routes.profile.path || destination === routes.career.path || destination === routes.jobs.path
    || destination === routes.interests.path || destination === routes.projects.path || destination === routes.workspace.path
    || destination === routes.interview.path || destination === routes.growth.path || destination === routes.applications.path
    ? destination + search : routes.dashboard.path
  const title = registering ? '注册账户' : '登录'

  if (checking) return <p className="surface auth-card" role="status">正在确认登录状态…</p>
  if (account) return <Navigate to={returnPath} replace />

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setError('')
    const form = new FormData(event.currentTarget)
    const password = String(form.get('password') ?? '')
    const cleanEmail = email.trim()
    if (registering && (!/\p{L}/u.test(password) || !/[^\p{L}\s]/u.test(password))) {
      setError('密码须包含字母以及数字或符号。')
      return
    }
    if (registering && String(form.get('username') ?? '').trim().length < 2) {
      setError('用户名至少需要 2 个字符。')
      return
    }
    setPending(true)
    try {
      if (registering) {
        await authApi.register(cleanEmail, String(form.get('username')).trim(), password)
        navigate(routes.login.path, { replace: true, state: { email: cleanEmail, registered: true, from: destination, search } })
      } else {
        await login(cleanEmail, password)
        navigate(returnPath, { replace: true })
      }
    } catch (failure) {
      setError(errorMessage(failure))
    } finally {
      setPending(false)
    }
  }

  return (
    <section className="surface auth-card" aria-labelledby="auth-title">
      <h1 id="auth-title">{title}</h1>
      {location.state?.registered && <p className="form-success" role="status">注册成功，请登录。</p>}
      <form className="account-form" onSubmit={submit}>
        {registering && <label>用户名<input name="username" autoComplete="nickname" required minLength={2} maxLength={64} /></label>}
        <label>邮箱<input name="email" type="email" autoComplete="username" required maxLength={254} value={email} onChange={(event) => setEmail(event.target.value)} /></label>
        <label>密码<input name="password" type="password" autoComplete={registering ? 'new-password' : 'current-password'} required minLength={registering ? 12 : undefined} maxLength={128} /></label>
        {registering && <p className="panel-description">至少 12 个字符，包含字母以及数字或符号。</p>}
        {error && <p className="form-error" role="alert">{error}</p>}
        <button className="button button-filled" disabled={pending}>{pending ? '正在提交…' : title}</button>
      </form>
      <p className="auth-switch">{registering ? '已有账户？' : '还没有账户？'}{' '}
        <Link to={registering ? routes.login.path : routes.register.path} state={{ from: destination, search }}>{registering ? '去登录' : '去注册'}</Link>
      </p>
    </section>
  )
}
