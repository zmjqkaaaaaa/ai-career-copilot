import { useState } from 'react'
import type { Diagnosis, Evaluation, Lesson, Task } from '../../services/learning'

export const masteryLabels: Record<string,string> = { verified: '已通过阶段测评', self_reported: '用户自述', inferred: '推断或参考', unknown: '待验证' }
export const states: Record<string,string> = { pending: '待开始', in_progress: '进行中', completed: '已完成', submitted: '已提交', needs_revision: '待修订' }

export function DiagnosisPanel({ data }: { data: Diagnosis }) {
  return <section className="surface detail-panel grid gap-3">
    <h2>六类能力诊断</h2>
    <div className="career-grid">{Object.entries(data.categories).map(([id, name]) => <article className="career-detail" key={id}>
      <h3>{name}</h3>
      {data.topics.filter((item) => item.category === id).map((item) => <details className="mt-2" key={item.topic}>
        <summary>{item.title} · {masteryLabels[item.status]}</summary>
        <p>置信度 · {item.confidence}{item.level != null && ` · 最近测评 ${item.level} 分`}</p>
        {item.last_verified_at && <p>最近测评 · {new Date(item.last_verified_at).toLocaleString()}</p>}
        {item.evidence.length ? <ul>{item.evidence.map((row, i) => <li key={i}>{row.source} #{row.ref} · {row.text}</li>)}</ul> :
          <p>当前没有可核对的证据。</p>}
      </details>)}
    </article>)}</div>
  </section>
}

export function TaskPanel({ task, busy, change, teach }: { task: Task; busy: boolean;
  change: (status: string, minutes: number) => void; teach: () => void }) {
  const [minutes, setMinutes] = useState(task.actual_minutes)
  return <article className="career-detail account-form">
    <h3>{task.data.title} · {states[task.status]}</h3>
    <p>{task.data.type} · 预计 {task.data.minutes} 分钟</p>
    <p>实践 · {task.data.exercise}</p><p>验收 · {task.data.acceptance}</p>
    {task.data.checkpoint && <p>今日目标 · {task.data.checkpoint}</p>}
    <label>实际学习时间（分钟）<input type="number" min={0} max={600} value={minutes}
      onChange={(e) => setMinutes(Math.max(0, Math.min(600, Number(e.target.value))))} /></label>
    <div className="career-actions">
      {task.status !== 'in_progress' && <button className="button button-outline" disabled={busy}
        onClick={() => change('in_progress', minutes)}>{task.status === 'completed' ? '重新学习' : '开始任务'}</button>}
      {task.status === 'in_progress' && <button className="button button-outline" disabled={busy} onClick={() => change('pending', minutes)}>暂停任务</button>}
      <button className="button button-outline" disabled={busy} onClick={() => change('completed', minutes)}>记录完成</button>
      <button className="button button-outline" onClick={teach}>前往导师和资料</button>
    </div>
  </article>
}

export function LessonPanel({ data }: { data: Lesson }) {
  return <div className="grid gap-2">
    {(data.text || data.explanation) && <p className="whitespace-pre-wrap">{data.text || data.explanation}</p>}
    {data.example && <pre className="overflow-auto whitespace-pre-wrap rounded bg-slate-50 p-2 text-xs">{data.example}</pre>}
    {data.question && <p><strong>理解小题</strong> · {data.question}</p>}
    {data.next_step && <p><strong>下一步</strong> · {data.next_step}</p>}
  </div>
}

export function FeedbackPanel({ item }: { item: Evaluation }) {
  return <div className="career-detail grid gap-2">
    <h3>{states[item.status]} · {item.score == null ? '证据不足' : item.score + ' / 100'} · 覆盖率 {item.coverage}%</h3>
    <p>{item.static.detail}</p>
    {item.fixture?.length ? <div><h4>固定样例 · 核对填报结果</h4><ul>{item.fixture.map((row) => <li key={row.case}>
      {row.case} · 你的结果 {row.observed ?? '未填写'} · 预期 {row.expected} · {row.passed ? '一致' : '待修订'}
    </li>)}</ul></div> : null}
    <p>正确部分 · {item.correct.join('；') || '无可引用结果'}</p><p>错误 · {item.errors.join('；') || '未指出'}</p>
    <p>缺失 · {item.missing.join('；') || '未指出'}</p>
    <p>修改建议 · {item.revision}</p><p>下一步 · {item.next_step}</p>
    <details><summary>查看评分依据</summary><ul>{item.ratings.map((row) => <li key={row.criterion}>
      {row.criterion} · {row.level == null ? '待验证' : row.level + '/4'} · {row.reason}{row.quote && ` · 「${row.quote}」`}
    </li>)}</ul></details>
  </div>
}

