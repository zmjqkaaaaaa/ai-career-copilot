import { Link } from 'react-router'
import { CalendarClock } from 'lucide-react'
import { routes } from '../routes'
import type { AppRoute } from '../routes'

export function ModulePlaceholderPage({ route }: { route: AppRoute }) {
  const Icon = route.icon

  return (
    <article className="surface placeholder">
      <span className="icon-tile" data-tone="violet"><Icon size={24} /></span>
      <span className="badge">待开发</span>
      <h1>{route.title}</h1>
      <p>{route.description}</p>
      <div className="placeholder-plan">
        <h2><CalendarClock size={18} /> 后续规划</h2>
        <ul>{route.planned.map((item) => <li key={item}>{item}</li>)}</ul>
      </div>
      <Link className="button button-outline" to={routes.dashboard.path}>返回求职驾驶舱</Link>
    </article>
  )
}
