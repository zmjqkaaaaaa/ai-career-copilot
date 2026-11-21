import { Link } from 'react-router'
import { modules } from '../../data/dashboardMock'
import { routes } from '../../routes'

export function CoreModules() {
  return (
    <section aria-labelledby="modules-title">
      <div className="section-heading"><h2 id="modules-title">核心能力模块</h2></div>
      <div className="module-grid">
        {modules.map(({ title, description, route, tone }) => {
          const Icon = route.icon
          const available = [routes.career.path, routes.jobs.path, routes.interests.path, routes.projects.path, routes.workspace.path, routes.growth.path].includes(route.path)
          const status = available ? '可使用' : '待开发'
          return (
            <Link className="surface module-card" key={route.path} to={route.path} aria-label={`进入模块：${title}，${status}`}>
              <div className="module-top">
                <span className="icon-tile" data-tone={tone}><Icon size={22} aria-hidden="true" /></span>
                <span className="badge" data-tone={available ? 'violet' : undefined}>{status}</span>
              </div>
              <h3>{title}</h3>
              <p>{description}</p>
              <span className="module-action">进入模块</span>
            </Link>
          )
        })}
      </div>
    </section>
  )
}
