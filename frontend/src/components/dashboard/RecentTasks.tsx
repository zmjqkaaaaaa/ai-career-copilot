import { tasks } from '../../data/dashboardMock'
import { useDemoTasks } from '../../hooks/useDemoTasks'

export function RecentTasks() {
  const { completed, toggle } = useDemoTasks()

  return (
    <section className="surface detail-panel" aria-labelledby="tasks-title">
      <div className="section-heading">
        <h2 id="tasks-title">近期任务</h2>
        <span className="badge">演示任务</span>
      </div>
      <p className="panel-description" role="status">已完成 {completed.length} / {tasks.length}</p>
      <ul className="task-list">
        {tasks.map(({ id, title }) => {
          const checked = completed.includes(id)
          return (
            <li key={id}>
              <label className="task-row">
                <input type="checkbox" checked={checked} onChange={() => toggle(id)} />
                <span className="task-title">{title}</span>
                <span className="task-status" aria-hidden="true" data-complete={checked}>{checked ? '已完成' : '待完成'}</span>
              </label>
            </li>
          )
        })}
      </ul>
    </section>
  )
}
