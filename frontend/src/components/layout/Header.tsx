import { Bell, ChevronRight, Menu, Search } from 'lucide-react'
import { useId, useState } from 'react'
import { Link } from 'react-router'
import { useAuth } from '../../hooks/AuthProvider'
import { routeList, routes } from '../../routes'
import type { AppRoute } from '../../routes'

type HeaderProps = {
  route: AppRoute
  menuOpen: boolean
  onMenuToggle: () => void
}

export function Header({ route, menuOpen, onMenuToggle }: HeaderProps) {
  const { account, checking } = useAuth()
  const [panel, setPanel] = useState<'search' | 'notifications' | null>(null)
  const [query, setQuery] = useState('')
  const panelId = useId()
  const keyword = query.trim().toLowerCase()
  const results = routeList.filter((item) => `${item.title} ${item.group}`.toLowerCase().includes(keyword))

  function togglePanel(next: typeof panel) {
    setPanel((current) => current === next ? null : next)
    setQuery('')
  }

  return (
    <header className="topbar" onKeyDown={(event) => {
      if (event.key === 'Escape' && panel) {
        document.getElementById(`${panelId}-${panel}`)?.focus()
        setPanel(null)
      }
    }}>
      <div className="topbar-leading">
        <button className="icon-button menu-toggle" type="button" aria-label={menuOpen ? '关闭导航' : '打开导航'} aria-expanded={menuOpen} aria-controls="app-sidebar" onClick={onMenuToggle}>
          <Menu size={21} />
        </button>
        <div className="topbar-heading">
          <nav className="breadcrumbs" aria-label="面包屑">
            {route.path === routes.dashboard.path
              ? <span>{route.group}</span>
              : <Link to={routes.dashboard.path}>工作台</Link>}
            {route.group !== '工作台' && <><ChevronRight size={13} aria-hidden="true" /><span>{route.group}</span></>}
            <ChevronRight size={13} aria-hidden="true" />
            <span aria-current="page">{route.title}</span>
          </nav>
          <div className="page-title">{route.title}</div>
        </div>
      </div>
      <div className="topbar-actions">
        <button id={`${panelId}-search`} className="search-button" type="button" aria-label="搜索模块" aria-expanded={panel === 'search'} aria-controls={panel === 'search' ? panelId : undefined} onClick={() => togglePanel('search')}>
          <Search size={18} aria-hidden="true" />
          <span>搜索模块</span>
        </button>
        <button id={`${panelId}-notifications`} className="icon-button notification-button" type="button" aria-label="通知" aria-expanded={panel === 'notifications'} aria-controls={panel === 'notifications' ? panelId : undefined} onClick={() => togglePanel('notifications')}>
          <Bell size={20} aria-hidden="true" />
        </button>
        {account
          ? <Link className="avatar" to={routes.profile.path} aria-label="查看个人档案">{Array.from(account.username)[0]}</Link>
          : !checking && <Link className="button button-outline" to={routes.login.path}>登录</Link>}
      </div>
      {panel === 'search' && (
        <div id={panelId} className="topbar-panel surface">
          <label htmlFor={`${panelId}-query`}>搜索本地模块</label>
          <input autoFocus id={`${panelId}-query`} type="search" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="例如：岗位匹配" />
          {results.length ? (
            <ul className="search-results">{results.map((item) => (
              <li key={item.path}><Link to={item.path} onClick={() => setPanel(null)}>{item.title}</Link></li>
            ))}</ul>
          ) : <p role="status">没有找到匹配的模块。</p>}
        </div>
      )}
      {panel === 'notifications' && (
        <div id={panelId} className="topbar-panel surface">
          <p className="panel-title">通知</p>
          <p>暂无通知。</p>
        </div>
      )}
    </header>
  )
}
