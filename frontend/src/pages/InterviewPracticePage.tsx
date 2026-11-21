import { useEffect, useRef, useState } from 'react'
import { useSearchParams } from 'react-router'
import { InterviewReport, References, scoreText } from '../components/interview/InterviewReport'
import { errorMessage } from '../services/api'
import { interview, type Detail, type Options, type Preparation, type Preview, type Report, type Session,
  type Setup, type Training, type Turn } from '../services/interview'

const TABS = { prepare: '面试准备', session: '模拟工作台', report: '面试报告', history: '面试历史', training: '训练中心' }
const INITIAL: Setup = { mode: 'technical', difficulty: 'beginner', style: 'coach', minutes: 15,
  deep_followup: true, teaching: false }
const STATES: Record<string,string> = { ready: '待开始', in_progress: '进行中', finished: '已结束' }
const ERRORS: Record<string,string> = { MODEL_TIMEOUT: '模型响应超时', MODEL_OUTPUT_INVALID: '模型输出格式异常',
  MODEL_OUTPUT_INCOMPLETE: '模型输出未完整返回', MODEL_CONFIG_CHANGED: '模型配置已变，请重新预览',
  INTERVIEW_PREVIEW_CHANGED: '任务资料已变，请重新预览' }

type Tab = keyof typeof TABS
type SourceOption = { id: number; label: string; version?: number }

function SourceSelect({ label, value, options, choose }: { label: string; value?: number; options: SourceOption[];
  choose: (id?: number) => void }) {
  return <label>{label}<select value={value ?? ''} onChange={(e) => choose(Number(e.target.value) || undefined)}>
    <option value="">{options.length ? '自动选择最新' : '暂无可用资料'}</option>
    {options.map((item) => <option key={item.id} value={item.id}>{item.label}{item.version !== undefined && ` · v${item.version}`}</option>)}
  </select></label>
}

export function InterviewPracticePage() {
  const [params, setParams] = useSearchParams()
  const id = Number(params.get('session')) || null
  const requested = params.get('tab')
  const tab: Tab = requested && Object.hasOwn(TABS, requested) ? requested as Tab : id ? 'session' : 'prepare'
  const [options, setOptions] = useState<Options | null>(null)
  const [setup, setSetup] = useState<Setup>(() => {
    const appointment = Number(params.get('schedule'))
    if (appointment > 0 && Number.isSafeInteger(appointment)) {
      return { ...INITIAL, mode: 'combined', interview_schedule_id: appointment }
    }
    const repository = Number(params.get('repository'))
    const commit = params.get('commit')
    return repository > 0 && Number.isSafeInteger(repository) ? {
      ...INITIAL, mode: 'project', repository_id: repository,
      commit: commit && /^[a-f0-9]{40}$/.test(commit) ? commit : undefined,
    } : INITIAL
  })
  const [autoStages, setAutoStages] = useState(true)
  const [prepared, setPrepared] = useState<{ data: Preparation; setup: Setup } | null>(null)
  const nonce = useRef<string | null>(null)
  const [detail, setDetail] = useState<Detail | null>(null)
  const [history, setHistory] = useState<Session[]>([])
  const [report, setReport] = useState<{ session: number; data: Report } | null>(null)
  const [training, setTraining] = useState<Training | null>(null)
  const [answer, setAnswer] = useState('')
  const activeQuestion = detail?.id === id ? detail.question?.id : undefined
  const [preview, setPreview] = useState<{ session: number; turn: Turn; data: Preview } | null>(null)
  const [confirmEnd, setConfirmEnd] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [tick, setTick] = useState(0)
  const [now, setNow] = useState(Date.now())
  const current = detail?.id === id ? detail : null
  const job = current?.task
  const pending = job?.state === 'queued' || job?.state === 'running'
  const blocked = busy || pending
  const seconds = current?.deadline ? Math.max(0, Math.ceil((Date.parse(current.deadline) - now) / 1000)) : null
  const stages = options?.stages ?? {}
  const repository = options?.repositories.find((item) => item.id === setup.repository_id) ?? options?.repositories[0]
  const sourceRepo = current?.sources.repository
  const slug = sourceRepo && typeof sourceRepo === 'object' && typeof sourceRepo.slug === 'string' ? sourceRepo.slug : undefined
  const preparedPlan = prepared?.data.sources.plan

  useEffect(() => {
    let ignore = false
    interview.options().then((data) => { if (!ignore) setOptions(data) })
      .catch((e) => { if (!ignore) setError(errorMessage(e)) })
    return () => { ignore = true }
  }, [])

  useEffect(() => {
    let ignore = false
    if (id) interview.detail(id).then((data) => { if (!ignore) setDetail(data) })
      .catch((e) => { if (!ignore) setError(errorMessage(e)) })
    if (tab === 'history') interview.history().then((data) => { if (!ignore) setHistory(data) })
      .catch((e) => { if (!ignore) setError(errorMessage(e)) })
    if (tab === 'training') interview.training().then((data) => { if (!ignore) setTraining(data) })
      .catch((e) => { if (!ignore) setError(errorMessage(e)) })
    return () => { ignore = true }
  }, [id, tab, tick])

  useEffect(() => {
    if (!id || current?.state !== 'finished' || tab !== 'report') return
    let ignore = false
    interview.report(id).then((data) => { if (!ignore) setReport({ session: id, data }) })
      .catch((e) => { if (!ignore) setError(errorMessage(e)) })
    return () => { ignore = true }
  }, [id, current?.state, tab, tick])

  useEffect(() => {
    if (!pending && !(current?.state === 'in_progress' && seconds === 0)) return
    const timer = window.setTimeout(() => setTick((n) => n + 1), 1400)
    return () => window.clearTimeout(timer)
  }, [pending, current?.state, seconds === 0, tick])

  useEffect(() => {
    if (current?.state !== 'in_progress') return
    const timer = window.setInterval(() => setNow(Date.now()), 1000)
    return () => window.clearInterval(timer)
  }, [current?.state])

  useEffect(() => {
    setAnswer('')
  }, [activeQuestion])

  function navigate(next: Tab, session = id) {
    setParams(session ? { session: String(session), tab: next } : { tab: next })
    setPreview(null); setError(''); setConfirmEnd(false)
    if (session !== id) setAnswer('')
  }

  function change(patch: Partial<Setup>) {
    setPrepared(null)
    nonce.current = null
    setSetup((value) => ({ ...value, ...patch }))
  }

  async function act(action: () => Promise<void>, refresh = true) {
    setError(''); setBusy(true)
    try { await action(); if (refresh) setTick((n) => n + 1) }
    catch (e) { setError(errorMessage(e)) }
    finally { setBusy(false) }
  }

  function review(turn: Turn) {
    if (!id) return
    void act(async () => { setPreview({ session: id, turn, data: await interview.preview(id, turn) }) }, false)
  }

  function choices(map: Record<string,string>) {
    return Object.entries(map).map(([key, label]) => <option key={key} value={key}>{label}</option>)
  }

  const readyReport = report?.session === id ? report.data : null
  return <div className="career-page">
    <section className="hero"><h1>AI 面试训练</h1><p>围绕目标岗位逐题练习，复盘回答中的证据、技术理解和改进动作。</p></section>
    <nav className="career-tabs" aria-label="面试训练分区">{Object.entries(TABS).map(([key, name]) =>
      <button key={key} className="button button-outline" aria-pressed={tab === key} onClick={() => navigate(key as Tab)}>{name}</button>)}</nav>
    {error && <p className="form-error" role="alert">{error}</p>}
    {tab === 'prepare' && options && <div className="career-columns">
      <section className="surface detail-panel"><h2>选择资料和训练方式</h2>
        <form className="account-form" onSubmit={(e) => {
          e.preventDefault()
          const value: Setup = { ...setup, target: setup.target?.trim() || undefined,
            ...(setup.commit && repository ? { repository_id: repository.id } : {}),
            stage_minutes: setup.mode === 'combined' && !autoStages ? setup.stage_minutes : undefined }
          void act(async () => {
            nonce.current = crypto.randomUUID()
            setPrepared({ data: await interview.prepare(value), setup: value })
          }, false)
        }}>
          <label>目标岗位<input placeholder={options.target} maxLength={150} value={setup.target ?? ''}
            onChange={(e) => change({ target: e.target.value })} /></label>
          <label>面试模式<select value={setup.mode} onChange={(e) => change({ mode: e.target.value })}>{choices(options.modes)}</select></label>
          <label>难度<select value={setup.difficulty} onChange={(e) => change({ difficulty: e.target.value })}>{choices(options.difficulties)}</select></label>
          <label>面试官风格<select value={setup.style} onChange={(e) => change({ style: e.target.value })}>{choices(options.styles)}</select></label>
          <label>总时长（分钟）<input type="number" required min={setup.mode === 'combined' ? 7 : 5} max={60}
            value={setup.minutes} onChange={(e) => change({ minutes: Number(e.target.value) })} /></label>
          {setup.interview_schedule_id ? <p>使用关联投递保存的 JD 和简历版本。</p> : <>
          <SourceSelect label="关联 JD" options={options.jobs} value={setup.job_id} choose={(job_id) => change({ job_id })} />
          <SourceSelect label="选择已确认简历" options={options.resumes} value={setup.resume_content_id}
            choose={(resume_content_id) => change({ resume_content_id })} />
          </>}
          <SourceSelect label="选择方案与 PRD" options={options.projects} value={setup.recommendation_id}
            choose={(recommendation_id) => change({ recommendation_id })} />
          <SourceSelect label="选择已导入仓库" options={options.repositories} value={setup.repository_id}
            choose={(repository_id) => change({ repository_id, commit: undefined })} />
          {repository && <label>仓库提交<select value={setup.commit ?? ''} onChange={(e) => change({ commit: e.target.value || undefined })}>
            <option value="">最新导入的提交</option>
            {repository.versions.map((sha) => <option key={sha} value={sha}>{sha.slice(0, 12)}</option>)}
          </select></label>}
          {setup.mode === 'combined' && <>
            <label><input type="checkbox" checked={autoStages} onChange={(e) => {
              setAutoStages(e.target.checked)
              change({ stage_minutes: Object.fromEntries(Object.keys(stages).map((key, index) =>
                [key, Math.floor(setup.minutes / 7) + Number(index < setup.minutes % 7)])) })
            }} /> 自动分配阶段时长</label>
            {!autoStages && Object.entries(stages).map(([key, label]) => <label key={key}>{label}（分钟）
              <input type="number" min={1} max={45} required value={setup.stage_minutes?.[key] ?? ''}
                onChange={(e) => change({ stage_minutes: { ...setup.stage_minutes, [key]: Number(e.target.value) } })} /></label>)}
          </>}
          <label><input type="checkbox" checked={setup.deep_followup} onChange={(e) => change({ deep_followup: e.target.checked })} /> 启用深度追问</label>
          <label><input type="checkbox" checked={setup.teaching} onChange={(e) => change({ teaching: e.target.checked })} /> 启用教学提示</label>
          <button className="button button-filled" disabled={busy}>核对面试准备</button>
        </form>
      </section>
      <section className="surface detail-panel">
        <h2>本场安排</h2>
        {prepared ? <>
          <p>{prepared.data.target} · {options.modes[prepared.setup.mode]}</p>
          <ul>{prepared.data.schedule.map((item) => <li key={item.stage}>{stages[item.stage]} · {item.questions} 道主题题{item.minutes && ` · ${item.minutes} 分钟`}</li>)}</ul>
          <p>{prepared.data.has_project_code ? '已找到仓库代码，项目题可引用对应版本。' : '当前无可引用的源码片段，项目题使用自述或假设情境。'}</p>
          {preparedPlan && typeof preparedPlan === 'object' && preparedPlan.version && <p>关联项目 PRD · 第 {preparedPlan.version} 版</p>}
          <button className="button button-filled mt-3" disabled={busy} onClick={() => void act(async () => {
            const row = await interview.create(prepared.setup, nonce.current!)
            navigate('session', row.id)
          })}>创建面试</button>
        </> : <p>核对后可查看题目安排和资料可用性。</p>}
      </section>
    </div>}
    {tab === 'session' && !current && <section className="surface detail-panel"><p>{id ? '正在读取面试…' : '请先创建一场面试。'}</p></section>}
    {tab === 'session' && current && <>
      <section className="surface detail-panel">
        <h2>{current.target} · {options?.modes[current.settings.mode]}</h2>
        <p>{STATES[current.state]} · 已答 {current.answered} 题 · 剩余约 {current.remaining} 道主题题</p>
        {current.state === 'in_progress' && seconds !== null && <p>剩余时间 · {Math.floor(seconds / 60)}:{String(seconds % 60).padStart(2, '0')}</p>}
        {pending && <p role="status">正在处理本轮…</p>}
        {job?.state === 'failed' && <div role="alert" className="form-error">
          <p>{ERRORS[job.error_code ?? ''] ?? '本轮处理失败'}（{job.error_code}）</p>
          {job.attempt < 3 && !['MODEL_CONFIG_CHANGED', 'INTERVIEW_PREVIEW_CHANGED'].includes(job.error_code ?? '') &&
            current.state !== 'finished' && seconds !== 0 &&
            <button className="button button-outline" disabled={blocked} onClick={() => void act(async () => { await interview.retry(current.id, job.id) })}>重试本轮</button>}
        </div>}
      </section>
      {preview?.session === current.id && <section className="surface detail-panel grid gap-3">
        <h2>核对发送内容</h2><p>模型服务 · {preview.data.model_host}</p>
        <pre className="max-h-64 overflow-auto whitespace-pre-wrap break-all text-xs">{JSON.stringify(preview.data.context, null, 2)}</pre>
        <div className="career-actions">
          <button className="button button-filled" disabled={blocked || seconds === 0} onClick={() => void act(async () => {
            await interview.send(current.id, preview.turn, preview.data.approval); setPreview(null)
          })}>同意发送并执行</button>
          <button className="button button-outline" onClick={() => setPreview(null)}>取消</button>
        </div>
      </section>}
      {current.state === 'ready' && <section className="surface detail-panel">
        <button className="button button-filled" disabled={blocked} onClick={() => review({ kind: 'start' })}>预览并开始面试</button>
      </section>}
      {current.state === 'in_progress' && <div className="grid min-w-0 gap-3 xl:grid-cols-[minmax(0,1fr)_minmax(0,2fr)_minmax(0,1fr)]">
        <aside className="surface detail-panel"><h2>进度与已问问题</h2>
          <ul className="grid gap-2">{current.questions.map((row) => <li className="break-words" key={row.id}>
            {row.ordinal}. {row.answered ? '已答' : '当前'} · {row.followup ? '追问' : stages[row.stage]}<p>{row.question}</p>
          </li>)}</ul>
        </aside>
        <section className="surface detail-panel">
          {current.question && seconds !== 0 ? <>
            <h2>{current.question.parent_id ? '动态追问' : '当前问题'}</h2>
            <p className="my-3 text-lg font-semibold">{current.question.question}</p>
            {current.question.hint && <p className="career-detail">教学提示 · {current.question.hint}</p>}
            <form className="account-form" onSubmit={(e) => {
              e.preventDefault(); review({ kind: 'answer', question_id: current.question!.id, answer: answer.trim() })
            }}>
              <label>我的回答<textarea required maxLength={3500} rows={7} value={answer}
                onChange={(e) => setAnswer(e.target.value)} /></label>
              <button className="button button-filled" disabled={blocked || !answer.trim()}>预览并提交回答</button>
            </form>
          </> : <p>{seconds === 0 ? '时间已到，正在整理复盘。' : '正在读取当前题目…'}</p>}
          <div className="career-actions mt-3">
            <button className="button button-outline" disabled={blocked} onClick={() => setConfirmEnd((old) => !old)}>{confirmEnd ? '继续面试' : '结束面试'}</button>
            {confirmEnd && <button className="button button-filled" disabled={blocked} onClick={() => void act(async () => {
              const result = await interview.finish(current.id); setReport({ session: current.id, data: result }); navigate('report')
            })}>确认结束并查看报告</button>}
          </div>
        </section>
        <aside className="surface detail-panel"><h2>当前考察</h2>
          <p>{current.question?.knowledge_point ?? '正在整理'}</p><p>教学提示 · {current.settings.teaching ? '开启' : '关闭'}</p>
          {slug && <p>关联仓库 · {slug}</p>}
          {current.question?.basis === 'scenario' && <p>假设情境题</p>}
          {current.question && <References rows={current.question.references} slug={slug} />}
        </aside>
      </div>}
      {current.state === 'finished' && <section className="surface detail-panel">
        <h2>本场面试已结束</h2><button className="button button-filled" onClick={() => navigate('report')}>查看面试复盘</button>
      </section>}
    </>}
    {tab === 'report' && (readyReport ? <InterviewReport report={readyReport} labels={stages} slug={slug} />
      : <section className="surface detail-panel"><p>{current?.state === 'finished' ? '正在读取报告…' : '完成面试后可查看报告。'}</p></section>)}
    {tab === 'history' && <section className="surface detail-panel grid gap-3">
      <h2>历史面试</h2>
      {!history.length && <p>暂无面试记录。</p>}
      {history.map((row) => <article className="career-detail" key={row.id}>
        <h3>{row.target} · {options?.modes[row.settings.mode]}</h3>
        <p>{new Date(row.created_at).toLocaleString()} · {STATES[row.state]}{row.state === 'finished' && ` · ${scoreText(row.score)}`}</p>
        <button className="button button-outline" onClick={() => navigate(row.state === 'finished' ? 'report' : 'session', row.id)}>
          {row.state === 'finished' ? '查看历史报告' : '继续这场面试'}</button>
      </article>)}
      {history.length > 0 && history.length % 30 === 0 && <button className="button button-outline" disabled={busy}
        onClick={() => void act(async () => { const rows = await interview.history(history.at(-1)?.id); setHistory([...history, ...rows]) }, false)}>查看更早记录</button>}
    </section>}
    {tab === 'training' && <section className="surface detail-panel grid gap-3">
      <h2>个性化训练</h2><p>已完成 {training?.done ?? 0} / {training?.total ?? 0} 项</p>
      {training?.tasks.map((task) => <article className="career-detail" key={task.id}>
        <h3>{task.title} · {task.priority === 'high' ? '优先' : '常规'}</h3>
        <p>{task.description}</p><p>验收 · {task.acceptance}</p><p>复练题 · {task.review_question}</p>
        <p>下次目标 · {task.next_goal}</p><p>计划日期 · {new Date(task.due_at).toLocaleDateString()}</p>
        <button className="button button-outline" disabled={busy} onClick={() => void act(async () => {
          await interview.changeTask(task.id, task.state === 'done' ? 'todo' : 'done')
        })}>{task.state === 'done' ? '已完成，恢复待做' : '标记完成'}</button>
      </article>)}
    </section>}
  </div>
}
