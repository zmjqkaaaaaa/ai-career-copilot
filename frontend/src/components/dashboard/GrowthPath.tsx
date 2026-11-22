import { BriefcaseBusiness, Compass, FilePenLine, FolderKanban, Target } from 'lucide-react'
import { growthSteps } from '../../data/dashboardContent'

const icons = [Target, Compass, FolderKanban, FilePenLine, BriefcaseBusiness]

export function GrowthPath() {
  return (
    <section className="surface detail-panel" aria-labelledby="growth-title">
      <div className="section-heading">
        <h2 id="growth-title">成长路径</h2>
        <span className="badge">示例路径</span>
      </div>
      <ol className="growth-path">
        {growthSteps.map((step, index) => {
          const Icon = icons[index]
          return (
            <li key={step} aria-current={index === 0 ? 'step' : undefined}>
              <span className="step-icon"><Icon size={20} aria-hidden="true" /></span>
              <strong>{step}</strong>
              {index === 0 && <small>当前阶段</small>}
            </li>
          )
        })}
      </ol>
    </section>
  )
}
