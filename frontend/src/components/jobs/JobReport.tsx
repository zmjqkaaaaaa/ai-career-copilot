import type { Gap, Match, Row } from '../../services/jobs'

export const importanceLabels: Record<string, string> = { required: '硬性要求', preferred: '优先条件', optional: '加分项', unknown: '重要性待确认' }
const statusLabels: Record<string, string> = {
  matched: '符合', partial: '部分符合', unmet: '明确不符',
  pending_not_provided: '待验证 · 尚未提供', pending_no_evidence: '待验证 · 暂无证据',
}
const evidenceLabels: Record<string, string> = { verified: '已验证', self_reported: '用户自述', inferred: 'AI 推断', unknown: '缺少信息' }
const dimensions: Record<string, string> = { education: '教育背景', product: '产品能力', ai: 'AI 技术', data: '编程与数据分析', practice: '项目实践', industry: '行业理解' }

function Evidence({ row }: { row: Row }) {
  return <div>
    <strong>{row.name}</strong> <span className="badge">{importanceLabels[row.importance]}</span>{' '}
    <span className="badge">{statusLabels[row.status]}</span>
    <blockquote>JD 原文 · {row.quote}</blockquote>
    <p>{evidenceLabels[row.evidence_status]}{row.sources.map((item, index) => <span className="block" key={index}>{item.quote}</span>)}</p>
  </div>
}

export function JobReport({ match, gaps, onAdvice, disabled }: {
  match: Match; gaps: Gap[]; onAdvice?: () => void; disabled?: boolean
}) {
  const { score_details: result } = match
  const advice = match.recommendations
  const lists: Record<string, string[]> = advice ? { 简历修改重点: advice.resume_focus, 面试准备: advice.interview_focus, 建议实践项目: advice.projects, 下一步行动: advice.next_steps } : {}
  return <div className="grid gap-4">
    <section className="surface detail-panel">
      <h2>匹配报告</h2>
      <p>参考匹配分 <strong>{match.overall_score === null ? '证据不足，暂未评分' : `${match.overall_score} / 100`}</strong></p>
      <p>证据覆盖率 <strong>{match.evidence_coverage === null ? '暂无可评硬性要求' : `${match.evidence_coverage}%`}</strong></p>
      <p className="panel-description">分数基于当前可判定的硬性要求。简历版本记录 #{match.content_id} · {match.scoring_version}</p>
      <p><strong>{result.verdict}</strong></p>
      {result.hard_flags.map((row) => <p key={row.ordinal}>硬性要求 · {row.name} · {row.status === 'matched' ? 'AI 推断，待核实' : statusLabels[row.status]}</p>)}
      <dl className="career-grid">{Object.entries(result.dimensions).map(([key, value]) =>
        <div className="career-detail" key={key}><dt>{dimensions[key]}（权重 {value.weight}%）</dt>
          <dd>{value.score ?? '待评分'} · 已判定 {value.rated}/{value.required}</dd></div>)}</dl>
    </section>
    <section className="surface detail-panel">
      <h2>逐项匹配及加分项</h2>
      <ul className="career-points">{result.requirements.map((row) => <li key={row.ordinal}><Evidence row={row} /></li>)}</ul>
    </section>
    <section className="surface detail-panel">
      <h2>能力差距详情</h2>
      {gaps.length === 0 && <p className="panel-description">暂无待核对的差距。</p>}
      {gaps.map((gap) => <details className="career-detail" key={gap.ordinal}>
        <summary>{gap.name} · {gap.priority}优先级 · {statusLabels[gap.status]}</summary>
        <Evidence row={gap} />
        <p>{gap.why}</p><p>提升方向 · {gap.action}</p><p>实践任务 · {gap.practice}</p><p>验证方式 · {gap.validation}</p>
      </details>)}
    </section>
    <section className="surface detail-panel">
      <h2>求职建议</h2>
      {advice && <><p>{advice.rationale}</p>{Object.entries(lists).map(([title, items]) => <div className="career-detail" key={title}>
        <h3>{title}</h3><ul>{items.map((item, index) => <li key={index}>{item}</li>)}</ul></div>)}</>}
      {onAdvice && <button className="button button-filled" disabled={disabled} onClick={onAdvice}>生成 AI 求职建议</button>}
    </section>
  </div>
}
