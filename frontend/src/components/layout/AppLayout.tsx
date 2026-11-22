import { useEffect, useState } from 'react'
import { matchPath, Outlet, useLocation } from 'react-router'
import { routeList, routes } from '../../routes'
import { Header } from './Header'
import { Sidebar } from './Sidebar'

export function AppLayout() {
  const { pathname } = useLocation()
  const route = routeList.find((item) => matchPath(item.path, pathname)) ?? routes.dashboard
  const [openPath, setOpenPath] = useState<string | null>(null)
  const menuOpen = openPath === pathname

  useEffect(() => {
    document.title = `${route.title} | AI Career Copilot`
  }, [route.title])

  useEffect(() => {
    window.scrollTo(0, 0)
  }, [pathname])

  useEffect(() => {
    if (!menuOpen) return
    const activeLink = document.querySelector<HTMLAnchorElement>('#app-sidebar .sidebar-link[aria-current="page"]')
    const focusTarget = activeLink ?? document.querySelector<HTMLAnchorElement>('#app-sidebar .brand')
    focusTarget?.focus()

    function onEscape(event: KeyboardEvent) {
      if (event.key === 'Escape') {
        setOpenPath(null)
        document.querySelector<HTMLButtonElement>('.menu-toggle')?.focus()
      }
    }

    window.addEventListener('keydown', onEscape)
    return () => window.removeEventListener('keydown', onEscape)
  }, [menuOpen])

  return (
    <>
      <a className="skip-link" href="#main-content">跳转到主要内容</a>
      <Sidebar open={menuOpen} onNavigate={() => {
        setOpenPath(null)
        if (menuOpen) document.getElementById('main-content')?.focus({ preventScroll: true })
      }} />
      {menuOpen && <button className="sidebar-scrim" type="button" aria-label="关闭侧栏" onClick={() => {
        setOpenPath(null)
        document.querySelector<HTMLButtonElement>('.menu-toggle')?.focus()
      }} />}
      <div className="app-content">
        <Header key={pathname} route={route} menuOpen={menuOpen} onMenuToggle={() => setOpenPath(menuOpen ? null : pathname)} />
        <main id="main-content" className="main-content" tabIndex={-1}><Outlet /></main>
      </div>
    </>
  )
}
