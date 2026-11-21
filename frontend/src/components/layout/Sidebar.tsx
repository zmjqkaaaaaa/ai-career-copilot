import { Sparkles } from 'lucide-react'
import { NavLink } from 'react-router'
import { LogoutButton } from '../auth/LogoutButton'
import { useAuth } from '../../hooks/AuthProvider'
import { navigationGroups, routes } from '../../routes'
import type { AppRoute } from '../../routes'

function SidebarLink({ route, onNavigate }: { route: AppRoute; onNavigate: () => void }) {
  const Icon = route.icon

  return (
    <NavLink className="sidebar-link" to={route.path} end onClick={onNavigate}>
      <Icon size={18} aria-hidden="true" />
      <span>{route.title}</span>
    </NavLink>
  )
}

export function Sidebar({ open, onNavigate }: { open: boolean; onNavigate: () => void }) {
  const { account, checking } = useAuth()
  return (
    <aside className="sidebar" id="app-sidebar" data-open={open}>
      <NavLink to={routes.dashboard.path} className="brand" onClick={onNavigate}>
        <span className="brand-symbol"><Sparkles size={21} aria-hidden="true" /></span>
        <span>AI Career <strong>Copilot</strong></span>
      </NavLink>
      <nav className="sidebar-nav" aria-label="主导航">
        {navigationGroups.map((group) => (
          <div className="nav-group" key={group.title}>
            <p>{group.title}</p>
            {group.items.map((route) => <SidebarLink key={route.path} route={route} onNavigate={onNavigate} />)}
          </div>
        ))}
      </nav>
      <div className="sidebar-footer">
        <SidebarLink route={routes.settings} onNavigate={onNavigate} />
        {account ? <>
          <NavLink to={routes.profile.path} onClick={onNavigate} className="account-link">
            <span className="avatar" aria-hidden="true">{Array.from(account.username)[0]}</span>
            <span className="min-w-0"><strong className="truncate">{account.username}</strong><small>求职者</small></span>
          </NavLink>
          <LogoutButton onNavigate={onNavigate} />
        </> : !checking && (
          <NavLink to={routes.login.path} onClick={onNavigate} className="account-link">
            <span className="avatar" aria-hidden="true">访</span>
            <span><strong>访客</strong><small>登录账户</small></span>
          </NavLink>
        )}
      </div>
    </aside>
  )
}
