import { useEffect, useState } from 'react'
import { applications, field, type Analytics, type Counts, type Metric, type Period, type Strategy } from '../../services/applications'
import { dateLabel, Panel, showFailure, type Run } from './shared'

const labels: Record<string, string> = {
  resume_passed: '简历通过率', written_passed: '笔试通过率', invited: '面试邀请率',
  interview_passed: '面试通过率', offer: 'Offer 转化率',
}

function ratio(metric?: Metric) {
  return metric ? `${metric.numerator}/${metric.denominator}${metric.rate === null ? ' · 样本不足' : ` · ${(metric.rate * 100).toFixed(1)}%`}` : '—'
}

export function Totals({ counts }: { counts: Counts }) {
  return <dl className="application-stats">
    <div><dt>累计投递</dt><dd>{counts.submitted}</dd></div>
    <div><dt>有效投递</dt><dd>{counts.valid}</dd></div>
    <div><dt>面试邀请</dt><dd>{counts.invited}</dd></div>
    <div><dt>收到 Offer</dt><dd>{counts.offer}</dd></div>
  </dl>
}

export function AnalyticsPanel({ data }: { data: Analytics | null }) {
  if (!data) return <p role="status">正在读取求职统计…</p>
  return <>
    <Panel title="求职统计">
      <Totals counts={data.summary} />
      <p>按 UTC 投递日期选取样本，统计这些投递目前已记录的进展。每个比例至少需要 {data.minimum_sample} 条对应样本。</p>
      <ul className="application-list">
        {Object.entries(data.summary.rates).map(([key, value]) => <li key={key}>{labels[key]} · {ratio(value)}</li>)}
      </ul>
      <h3>投递趋势</h3>
      {data.trend.length ? <ul className="application-list" aria-label="按日投递趋势">
        {data.trend.map((row) => <li key={row.date} className="flex flex-wrap items-center gap-2">
          <time>{row.date}</time><meter min={0} max={Math.max(...data.trend.map((item) => item.count))} value={row.count} aria-label={`${row.date} 投递数量`} /> {row.count} 份
        </li>)}
      </ul> : <p>该时段暂无已投递记录。</p>}
    </Panel>
    {[{ title: '按岗位', rows: data.by_position }, { title: '按简历版本', rows: data.by_resume }].map(({ title, rows }) =>
      <Panel title={title} key={title}>
        {rows.length ? <div className="overflow-x-auto"><table className="application-table">
          <thead><tr><th>名称</th><th>有效投递</th><th>面试邀请率</th><th>Offer 转化率</th></tr></thead>
          <tbody>{rows.map((row, index) => <tr key={index}><th scope="row">{row.label}</th><td>{row.valid}</td>
            <td>{ratio(row.rates.invited)}</td><td>{ratio(row.rates.offer)}</td></tr>)}</tbody>
        </table></div> : <p>暂无样本。</p>}
      </Panel>)}
  </>
}

export function PeriodForm({ select }: { select: (value: Period) => void }) {
  return <form className="account-form" onSubmit={(event) => {
    event.preventDefault()
    const data = new FormData(event.currentTarget)
    const start = field(data, 'start'), end = field(data, 'end')
    select({ ...(start ? { start } : {}), ...(end ? { end } : {}) })
  }}>
    <div className="career-grid"><label>投递开始日期（UTC）<input name="start" type="date" /></label>
      <label>投递截止日期（UTC）<input name="end" type="date" /></label></div>
    <div><button className="button button-outline">应用统计时段</button></div>
  </form>
}

const sections = { observations: '观察', inferences: 'AI 推断', hypotheses: '待验证假设', priority_actions: '优先行动' } as const

export function StrategyPanel({ period, run, busy, error }: {
  period: Period; run: Run; busy: boolean; error: (message: string) => void
}) {
  const [preview, setPreview] = useState<(Awaited<ReturnType<typeof applications.strategyPreview>> & { period: Period }) | null>(null)
  const [reports, setReports] = useState<Strategy[]>([])
  const [report, setReport] = useState<Strategy | null>(null)
  useEffect(() => {
    let ignore = false
    applications.reports().then((data) => { if (!ignore) setReports(data) })
      .catch((failure) => { if (!ignore) showFailure(failure, error) })
    return () => { ignore = true }
  }, [error])

  useEffect(() => {
    const current = report
    if (!current || !['queued', 'running'].includes(current.state)) return
    let ignore = false
    const timer = window.setTimeout(() => {
      applications.report(current.id).then((updated) => {
        if (!ignore) {
          setReport((active) => active?.id === current.id ? updated : active)
          setReports((all) => [updated, ...all.filter((row) => row.id !== updated.id)])
        }
      }).catch((failure) => { if (!ignore) showFailure(failure, error) })
    }, 1200)
    return () => { ignore = true; window.clearTimeout(timer) }
  }, [report, error])

  return <>
    <Panel title="AI 求职策略">
      <p>先核对将发送的统计摘要。摘要包含计数、日期和匿名分组。</p>
      <div><button className="button button-outline" disabled={busy} onClick={() => void run(async () => {
        setPreview({ ...await applications.strategyPreview(period), period })
      }, false)}>预览策略分析数据</button></div>
      {preview && <div className="application-preview">
        <p>接收服务 {preview.host}</p><pre>{JSON.stringify(preview.payload, null, 2)}</pre>
        <div className="flex flex-wrap gap-2">
          <button className="button button-filled" disabled={busy} onClick={() => void run(async () => {
            const row = await applications.analyze({ ...preview.period, approval: preview.approval })
            setReport(row); setReports((all) => [row, ...all.filter((item) => item.id !== row.id)]); setPreview(null)
          }, false)}>确认发送并分析</button>
          <button className="button button-outline" onClick={() => setPreview(null)}>取消</button>
        </div>
      </div>}
      <ul className="application-list">{reports.map((item) => <li key={item.id}>
        <button className="application-link" onClick={() => setReport(item)}>
          {item.statistics.start} 至 {item.statistics.end} · {dateLabel(item.created_at)}
        </button>
      </li>)}</ul>
    </Panel>
    {report && <Panel title="求职策略报告">
      <Totals counts={report.statistics.summary} />
      {report.statistics.sample_insufficient && <p role="status">有效样本不足，暂不判断简历质量或比较转化表现。</p>}
      {['queued', 'running'].includes(report.state) && <p role="status">策略分析处理中。</p>}
      {report.state === 'failed' && <p role="alert">分析失败（{report.error_code}）。请重新预览后重试。</p>}
      {report.analysis && <div className="application-panel">
        <h3>当前求职状态</h3><p>{report.analysis.current_state}</p>
        {Object.entries(sections).map(([key, label]) => {
          const items = report.analysis?.[key as keyof typeof sections] ?? []
          return items.length > 0 && <div key={key}><h3>{label}</h3><ul className="application-list">
            {items.map((item, index) => <li key={index}>{item}</li>)}
          </ul></div>
        })}
        <h3>下一阶段目标</h3><p>{report.analysis.next_goal}</p>
      </div>}
    </Panel>}
  </>
}
