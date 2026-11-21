import { Navigate, Outlet, useLocation } from 'react-router'
import { useAuth } from '../../hooks/AuthProvider'
import { routes } from '../../routes'

export function ProtectedRoute() {
  const { account, checking, authError, retrySession } = useAuth()
  const location = useLocation()
  if (checking) return <p className="surface auth-card" role="status">正在确认登录状态…</p>
  if (authError) return <div className="surface auth-card">
    <p role="alert">{authError}</p>
    <button className="button button-outline" onClick={retrySession}>重试</button>
  </div>
  return account ? <Outlet /> : <Navigate to={routes.login.path} state={{ from: location.pathname, search: location.search }} replace />
}
