import { Link } from 'react-router'
import { modules } from '../../data/dashboardContent'

export function CoreModules() {
  return (
    <section aria-labelledby="modules-title">
      <div className="section-heading"><h2 id="modules-title">核心能力模块</h2></div>
      <div className="module-grid">
        {modules.map(({ title, description, route, tone }) => {
          const Icon = route.icon
          return (
            <Link className="surface module-card" key={route.path} to={route.path} aria-label={`进入模块：${title}`}>
              <div className="module-top">
                <span className="icon-tile" data-tone={tone}><Icon size={22} aria-hidden="true" /></span>
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
