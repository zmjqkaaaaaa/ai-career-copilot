import { useEffect, useState } from 'react'
import { Link, useSearchParams } from 'react-router'
import { AnalyticsPanel, PeriodForm, StrategyPanel, Totals } from '../components/applications/Analytics'
import { Pipeline } from '../components/applications/Pipeline'
import { Positions } from '../components/applications/Positions'
import { ResumeVersions } from '../components/applications/ResumeVersions'
import { Schedules } from '../components/applications/Schedules'
import { appointmentTime, dateLabel, JobName, Panel } from '../components/applications/shared'
import { errorMessage } from '../services/api'
import { applications, statuses, type Analytics, type Period, type ResumeVersion } from '../services/applications'

const tabs = {
  overview: '求职概览', positions: '岗位发现', favorites: '岗位收藏', versions: '简历版本',
  board: '投递看板', schedules: '面试日程', analytics: '求职统计', strategy: 'AI 策略',
} as const
type Tab = keyof typeof tabs
type PipelineData = Awaited<ReturnType<typeof applications.pipeline>>

export function ApplicationWorkspacePage() {
  const [params, setParams] = useSearchParams()
  const name = params.get('tab')
  const tab = name && Object.hasOwn(tabs, name) ? name as Tab : 'overview'
  const job = Number(params.get('job')) || null
  const application = Number(params.get('application')) || null
  const version = Number(params.get('version')) || null
  const [pipeline, setPipeline] = useState<PipelineData | null>(null)
  const [versions, setVersions] = useState<ResumeVersion[]>([])
  const [analytics, setAnalytics] = useState<Analytics | null>(null)
  const [overview, setOverview] = useState<Analytics | null>(null)
  const [period, setPeriod] = useState<Period>({})
  const [refresh, setRefresh] = useState(0)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    let active = true
    Promise.all([applications.pipeline(), applications.versions(), applications.analytics({})])
      .then(([data, items, counts]) => {
        if (active) { setPipeline(data); setVersions(items); setOverview(counts) }
      }).catch((failure) => { if (active) setError(errorMessage(failure)) })
    return () => { active = false }
  }, [refresh])

  useEffect(() => {
    if (tab !== 'analytics') return
    let active = true
    applications.analytics(period).then((data) => { if (active) setAnalytics(data) })
      .catch((failure) => { if (active) setError(errorMessage(failure)) })
    return () => { active = false }
  }, [period, refresh, tab])

  async function run(action: () => Promise<void>, reload = true) {
    setBusy(true); setError('')
    try { await action(); if (reload) setRefresh((value) => value + 1) }
    catch (failure) {
      setError(errorMessage(failure))
      if (reload) setRefresh((value) => value + 1)
    } finally { setBusy(false) }
  }
  function choose(next: Tab, key?: string, id?: number) {
    setError('')
    setParams(key && id ? { tab: next, [key]: String(id) } : { tab: next })
  }

  const records = Object.values(pipeline?.columns ?? {}).flat()
    .sort((first, second) => second.updated_at.localeCompare(first.updated_at) || second.id - first.id)
  return <div className="career-page application-workspace">
    <section className="hero"><h1>求职执行工作台</h1><p>管理目标岗位、投递版本和面试进度。</p></section>
    <nav className="career-tabs" aria-label="求职执行视图">
      {Object.entries(tabs).map(([key, label]) =>
        <Link key={key} className={`button ${key === tab ? 'button-filled' : 'button-outline'}`}
          to={`?tab=${key}`} onClick={() => setError('')} aria-current={key === tab ? 'page' : undefined}>{label}</Link>)}
    </nav>
    {error && <p className="form-error" role="alert">{error}</p>}
    {tab === 'overview' && <Panel title="求职概览">
      <p>目标岗位 · {pipeline?.target || '尚未在个人档案设置'}</p>
      {overview && <Totals counts={overview.summary} />}
      {!pipeline && !error && <p role="status">正在读取工作台…</p>}
      <div className="career-grid">
        <div><h3>下一步行动</h3><ul className="application-list">
          {records.filter((row) => row.next_action && !['offer', 'rejected', 'withdrawn'].includes(row.current_status)).slice(0, 5)
            .map((row) => <li key={row.id}><Link className="application-link" to={`?tab=board&application=${row.id}`}><JobName row={row} /></Link><span>{row.next_action}</span></li>)}
          {!records.some((row) => row.next_action && !['offer', 'rejected', 'withdrawn'].includes(row.current_status)) && <li>暂无待办事项。</li>}
        </ul></div>
        <div><h3>即将到来的面试</h3><ul className="application-list">
          {pipeline?.upcoming.map((row) => <li key={row.id}>
            <Link className="application-link" to={`?tab=schedules&application=${row.application_id}&schedule=${row.id}`}>{row.position}</Link>
            <span>{appointmentTime(row)} · {row.timezone}</span>
          </li>)}
          {!pipeline?.upcoming.length && <li>暂无即将到来的面试。</li>}
        </ul></div>
      </div>
      <h3>最近求职动态</h3><ul className="application-list">
        {records.slice(0, 5).map((row) => <li key={row.id}>
          <Link className="application-link" to={`?tab=board&application=${row.id}`}><JobName row={row} /></Link>
          <span>{statuses[row.current_status]} · {dateLabel(row.updated_at)}</span>
        </li>)}
        {!records.length && <li><Link className="application-link" to="?tab=positions">录入一个岗位开始记录</Link></li>}
      </ul>
    </Panel>}
    {(tab === 'positions' || tab === 'favorites') && <Positions key={tab} favorites={tab === 'favorites'} selected={job}
      select={(id) => choose(tab, 'job', id)} versions={versions} refresh={refresh} run={run} error={setError}
      applied={() => choose('board')} busy={busy} />}
    {tab === 'versions' && <ResumeVersions key={`${job}-${version}`} target={job} selected={version}
      versions={versions} run={run} error={setError} busy={busy} />}
    {tab === 'board' && <Pipeline columns={pipeline?.columns} selected={application} select={(id) => choose('board', 'application', id)}
      versions={versions} refresh={refresh} run={run} error={setError} busy={busy} />}
    {tab === 'schedules' && <Schedules records={records} target={application}
      selectedId={Number(params.get('schedule')) || null} run={run} error={setError} refresh={refresh} busy={busy} />}
    {(tab === 'analytics' || tab === 'strategy') && <Panel title="统计时段">
      <PeriodForm select={(value) => { setPeriod(value); setError('') }} />
      <p>{period.start ?? '起始不限'} 至 {period.end ?? '今天'} · UTC</p>
    </Panel>}
    {tab === 'analytics' && <AnalyticsPanel data={analytics} />}
    {tab === 'strategy' && <StrategyPanel period={period} run={run} busy={busy} error={setError} />}
  </div>
}
