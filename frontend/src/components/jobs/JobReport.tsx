import { Link } from 'react-router'
import { useId, type ReactNode } from 'react'
import { resumeVersionPath, type Gap, type Match, type Row } from '../../services/jobs'

export const importanceLabels: Record<string, string> = { required: '硬性要求', preferred: '优先条件', optional: '加分项', unknown: '重要性待确认' }
const statusLabels: Record<string, string> = {
  matched: '符合', partial: '部分符合', unmet: '明确不符',
  pending_not_provided: '待核实 · 证据不足', pending_no_evidence: '待核实 · 条件未确认', pending_interview: '待面试核实',
}
const evidenceLabels: Record<string, string> = { verified: '已验证', self_reported: '用户自述', inferred: '间接证据，需核实', unknown: '缺少信息' }
const dimensions: Record<string, string> = { education: '教育背景', product: '产品能力', ai: 'AI 技术', data: '编程与数据分析', practice: '项目实践', industry: '行业理解' }

function Evidence({ row }: { row: Row }) {
  return <div>
    <strong>{row.name}</strong> <span className="badge">{importanceLabels[row.importance]}</span>{' '}
    <span className="badge">{statusLabels[row.status]}</span>
    <blockquote>JD 原文 · {row.quote}</blockquote>
    <p>{evidenceLabels[row.evidence_status]}</p>
    {row.sources.map((item, index) => <blockquote key={index}>
      {item.block_number ? '简历原文 · 段落 ' + item.block_number : item.location || '参考材料'} · {item.quote}
    </blockquote>)}
    {row.checks && row.checks.length > 1 && <ul>{row.checks.map((check) => <li key={check.name}>
      {check.name} · {check.sources.length ? `有相关经历（段落 ${check.sources.map((source) => source.block_number).join('、')}）` : '待补经历证据'}
    </li>)}</ul>}
    {row.interpretation && <p>{row.interpretation}</p>}
  </div>
}

export function JobReport({ match, gaps, adviceControls }: {
  match: Match; gaps: Gap[]; adviceControls?: ReactNode
}) {
  const adviceHeading = useId()
  const { score_details: result } = match
  const priorityOrder: Record<string, number> = { 高: 0, 中: 1, 低: 2 }
  const orderedGaps = [...gaps].sort((a, b) => (priorityOrder[a.priority] ?? 3) - (priorityOrder[b.priority] ?? 3) || a.ordinal - b.ordinal)
  const advice = match.recommendations
  const lists: Record<string, string[]> = advice ? { 简历修改重点: advice.resume_focus, 面试准备: advice.interview_focus, 建议实践项目: advice.projects, 下一步行动: advice.next_steps } : {}
  return <div className="grid gap-4">
    <section className="surface detail-panel">
      <h2>匹配报告</h2>
      <p>参考匹配分 <strong>{match.overall_score === null ? '证据不足，暂未评分' : `${match.overall_score} / 100`}</strong></p>
      <p>证据覆盖率 <strong>{match.evidence_coverage === null ? '暂无可评硬性要求' : `${match.evidence_coverage}%`}</strong></p>
      <p className="panel-description">参考分基于已评估的硬性要求，待核实项暂不计分。计算规则 {match.scoring_version}</p>
      <p>本次使用的简历 {match.resume
        ? <Link className="text-brand underline" to={resumeVersionPath(match.resume)}>{match.resume.original_filename} · 第 {match.resume.version} 版</Link>
        : '暂时无法定位原简历版本'}</p>
      <p><strong>{result.verdict}</strong></p>
      {result.hard_flags.map((row) => <p key={row.ordinal}>硬性要求 · {row.name} · {row.evidence_status === 'inferred' ? '有间接证据，待核实' : statusLabels[row.status]}</p>)}
      <dl className="career-grid">{Object.entries(result.dimensions).map(([key, value]) =>
        <div className="career-detail" key={key}><dt>{dimensions[key]}（权重 {value.weight}%）</dt>
          <dd>{value.required === 0 ? '本 JD 无硬性要求' : `${value.score ?? '待核实'} · 已评估 ${value.rated}/${value.required} 项`}</dd></div>)}</dl>
    </section>
    <section className="surface detail-panel">
      <h2>逐项匹配及加分项</h2>
      <ul className="career-points">{result.requirements.map((row) => <li key={row.ordinal}><Evidence row={row} /></li>)}</ul>
    </section>
    <section className="surface detail-panel">
      <h2>能力差距详情</h2>
      {gaps.length === 0 && <p className="panel-description">暂无待核对的差距。</p>}
      {orderedGaps.map((gap) => <details className="career-detail" key={gap.ordinal}>
        <summary>{gap.name} · {gap.priority}优先级 · {statusLabels[gap.status]}</summary>
        <Evidence row={gap} />
        <p>{gap.why}</p><p>提升方向 · {gap.action}</p><p>实践任务 · {gap.practice}</p><p>验证方式 · {gap.validation}</p>
      </details>)}
    </section>
    <section className="surface detail-panel" aria-labelledby={adviceHeading}>
      <h2 id={adviceHeading}>求职建议</h2>
      {advice && <>{advice.generation_method === 'local_fallback' && <p className="panel-description">AI 返回内容未能读取。以下是根据当前匹配结果生成的本地建议。</p>}
        <p>{advice.rationale}</p>{Object.entries(lists).filter(([, items]) => items.length).map(([title, items]) => <div className="career-detail" key={title}>
        <h3>{title}</h3><ul>{items.map((item, index) => <li key={index}>{item}</li>)}</ul></div>)}</>}
      {adviceControls}
    </section>
  </div>
}
