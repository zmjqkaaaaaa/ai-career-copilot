import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import type { Anchor, CareerReport, EvidenceStatus, Point } from '../../services/career'

const statusNames: Record<EvidenceStatus, string> = {
  verified: '已验证', self_reported: '简历自述', inferred: 'AI 推断', unknown: '证据不足',
}

function Sources({ sources }: { sources: Anchor[] }) {
  if (!sources.length) return null
  return <details className="career-detail">
    <summary>查看原文证据（{sources.length}）</summary>
    {sources.map(({ block_number, quote }, index) => <blockquote key={index}>段落 {block_number} · {quote}</blockquote>)}
  </details>
}

function Points({ title, values }: { title: string; values: Point[] }) {
  return <section className="surface detail-panel">
    <h3>{title}</h3>
    {values.length ? <ul className="career-points">{values.map((point, index) => <li key={index}>
      <strong>{point.title}</strong><p>{point.reason}</p><Sources sources={point.sources} />
    </li>)}</ul> : <p className="panel-description">暂无可展示内容。</p>}
  </section>
}

export function EvidenceReport({ result }: { result: CareerReport }) {
  const { analysis, report } = result
  const counts = (Object.keys(statusNames) as EvidenceStatus[]).map((status) => ({
    name: statusNames[status], count: report.skills.filter((skill) => skill.status === status).length,
  }))

  return (
    <div className="grid gap-4">
      <p className="panel-description">分析方向 {analysis.target_direction} · 模型 {analysis.model_name} · Prompt {analysis.prompt_version}</p>
      <Points title="基础背景与综合判断" values={[report.summary]} />
      <section className="surface detail-panel">
        <h3>能力证据分布</h3>
        <p className="panel-description">图表统计各状态的能力条目数。证据不足时显示「未评估」。</p>
        <p className="panel-description">{counts.map((entry) => `${entry.name} ${entry.count} 项`).join(' · ')}</p>
        <div className="h-52 w-full min-w-0">
          <ResponsiveContainer width="100%" height="100%" minWidth={0}>
            <BarChart data={counts} margin={{ top: 12, right: 12, left: -16 }}>
              <CartesianGrid strokeDasharray="3 3" vertical={false} />
              <XAxis dataKey="name" fontSize={12} />
              <YAxis allowDecimals={false} />
              <Tooltip formatter={(value) => [value, '能力条目数']} />
              <Bar dataKey="count" fill="#594bc8" radius={[4, 4, 0, 0]} isAnimationActive={false} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </section>
      <div className="career-grid">
        {report.skills.map((skill) => <article className="surface detail-panel" key={skill.name}>
          <div className="section-heading"><h3>{skill.name}</h3><span className="badge" data-tone="violet">{statusNames[skill.status]}</span></div>
          <p className="panel-description">{skill.category} · {skill.level}</p><p>{skill.reason}</p>
          <Sources sources={skill.sources} />
        </article>)}
      </div>
      <div className="career-grid">
        <Points title="教育背景" values={report.education} />
        <Points title="项目经历与实践" values={report.project_practice} />
        <Points title="核心优势" values={report.strengths} />
        <Points title="当前证据差距" values={report.gaps} />
        <Points title="岗位方向建议" values={report.directions} />
        <Points title="推荐项目类型" values={report.recommended_projects} />
        <Points title="下一步提升建议" values={report.next_steps} />
      </div>
    </div>
  )
}
