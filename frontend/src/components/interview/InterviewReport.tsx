import type { Reference, Report } from '../../services/interview'

export const scoreText = (score: number | null | undefined) => score == null ? '证据不足' : `${score} / 100`

export function References({ rows, slug }: { rows: Reference[]; slug?: string }) {
  if (!rows.length) return null
  return <div className="grid gap-2">{rows.map((row) => <details className="career-detail" key={row.id}>
    <summary>{row.path ? `${row.path} · ${row.start}–${row.end}` : row.id}</summary>
    {slug && row.path && row.commit && <a className="text-brand underline" target="_blank" rel="noreferrer"
      href={`https://github.com/${slug}/blob/${row.commit}/${row.path.split('/').map(encodeURIComponent).join('/')}#L${row.start}-L${row.end}`}>核对代码</a>}
    {row.text && <pre className="max-h-48 overflow-auto whitespace-pre-wrap text-xs">{row.text}</pre>}
  </details>)}</div>
}

export function InterviewReport({ report, labels, slug }: { report: Report; labels: Record<string,string>; slug?: string }) {
  return <>
    <section className="surface detail-panel grid gap-3">
      <h2>面试复盘 · {report.target}</h2>
      <p>辅助练习参考分 · {scoreText(report.score)} · 证据覆盖率 {report.coverage ?? 0}%</p>
      <p>完成 {report.answered} 题 · 用时 {Math.floor(report.duration_seconds / 60)} 分 {report.duration_seconds % 60} 秒</p>
      <p>待覆盖阶段 · {report.unassessed_stages.map((stage) => labels[stage] ?? stage).join('、') || '已覆盖全部计划阶段'}</p>
      <div className="career-grid">{Object.entries(report.stages).map(([stage, value]) =>
        <div className="career-detail" key={stage}><strong>{labels[stage] ?? stage}</strong><p>{scoreText(value.score)} · {value.answered} 题</p></div>)}</div>
      <details className="career-detail"><summary>查看各评分维度</summary>
        <ul>{report.dimensions.map((item) => <li key={item.type + item.key}>{item.label} · {scoreText(item.score)} · {item.evidence_count} 条评分</li>)}</ul>
      </details>
    </section>
    <section className="surface detail-panel grid gap-3">
      <h2>优势与待改进项</h2>
      {!report.strengths.length && <p>当前尚无足够证据标注优势。</p>}
      {report.strengths.map((item) => <p key={item.question_id}>优势 · {item.knowledge_point} · {item.feedback.join('、')}</p>)}
      {report.weaknesses.map((item) => <article className="career-detail" key={item.question_id}>
        <h3>{item.knowledge_point}</h3><p>{item.feedback.join('；') || '需要更多作答证据'}</p>
        <p>知识与思路 · {item.knowledge}</p><p>练习 · {item.exercise}</p><p>验收 · {item.acceptance}</p>
      </article>)}
      <div><h3>贡献与练习依据</h3>
        <p>本人陈述 · {report.contributions.join('；') || '本场未记录个人贡献声明'}</p>
        <p>已有项目测验记录 · {report.practice_evidence.join('；') || '暂无所选版本的测验记录'}</p>
      </div>
    </section>
    <section className="surface detail-panel grid gap-3">
      <h2>逐题复盘</h2>
      {report.turns.map((turn) => <details className="career-detail" key={turn.question_id}>
        <summary>{turn.question}</summary>
        <p className="whitespace-pre-wrap">我的回答 · {turn.answer}</p>
        <p>单题参考 · {scoreText(turn.score)} · 覆盖率 {turn.coverage}%</p>
        <p>改进思路 · {turn.corrected_idea}</p>
        <p>答法结构 · {turn.answer_outline.join(' → ') || '可先给出观点，再用一个事实验证'}</p>
        <ul>{turn.ratings.map((row) => <li key={row.key}>
          {row.label} · {scoreText(row.score)} · {row.reason}{row.quote && <blockquote>「{row.quote}」</blockquote>}
        </li>)}</ul>
        <References rows={turn.references} slug={slug} />
      </details>)}
      {!report.turns.length && <p>本场没有已评分的回答。</p>}
    </section>
  </>
}
