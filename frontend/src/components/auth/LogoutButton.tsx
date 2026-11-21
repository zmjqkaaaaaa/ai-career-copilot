import { LogOut } from 'lucide-react'
import { useState } from 'react'
import { useNavigate } from 'react-router'
import { useAuth } from '../../hooks/AuthProvider'
import { routes } from '../../routes'
import { errorMessage } from '../../services/api'

export function LogoutButton({ onNavigate }: { onNavigate: () => void }) {
  const { logout } = useAuth()
  const navigate = useNavigate()
  const [pending, setPending] = useState(false)
  const [error, setError] = useState('')

  async function submit() {
    setPending(true)
    setError('')
    try {
      await logout()
      onNavigate()
      navigate(routes.login.path, { replace: true })
    } catch (failure) {
      setError(errorMessage(failure))
    } finally {
      setPending(false)
    }
  }

  return <>
    <button className="sidebar-link w-full" type="button" disabled={pending} onClick={submit}>
      <LogOut size={18} aria-hidden="true" />{pending ? '正在退出…' : '退出登录'}
    </button>
    {error && <p className="form-error" role="alert">{error}</p>}
  </>
}
