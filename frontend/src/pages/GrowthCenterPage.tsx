import { Feedback } from '../components/common/Feedback'
import { useEffect, useRef, useState } from 'react'
import { Link, useSearchParams } from 'react-router'
import { DiagnosisPanel, FeedbackPanel, LessonPanel, TaskPanel, masteryLabels, states } from '../components/learning/LearningPanels'
import { errorMessage } from '../services/api'
import { learning, type AIAction, type Assignment, type Catalog, type Job, type Message,
  type InterviewSource, type Path, type Preview, type Progress, type Resource, type Session, type Submission, type Task } from '../services/learning'

const tabs = { home: '成长概览', diagnosis: '能力诊断', path: '学习路线', daily: '每日任务', mentor: 'AI 导师',
  resources: '学习资料', assignment: '作业中心', exam: '阶段测评', report: '成长报告' }
type Tab = keyof typeof tabs
const kinds = { text: '文本回答', markdown: 'Markdown', code: '代码片段', analysis: '产品分析报告', prd: 'PRD 文档', github: 'GitHub 链接' }
const messages = { MODEL_TIMEOUT: '模型响应超时', MODEL_OUTPUT_INVALID: '模型返回无法解析',
  MODEL_CONFIG_CHANGED: '模型配置已更新，请重新核对发送内容', LEARNING_PREVIEW_CHANGED: '待发送内容已更新' }
const dateKey = () => new Intl.DateTimeFormat('sv-SE').format(new Date())

export function GrowthCenterPage() {
  const [params, setParams] = useSearchParams()
  const requested = params.get('tab')
  const tab: Tab = requested && Object.hasOwn(tabs, requested) ? requested as Tab : 'home'
  const sessionId = Number(params.get('session')) || null
  const assessmentId = Number(params.get('assessment')) || null
  const reportId = Number(params.get('report')) || null
  const topic = params.get('topic') || 'python'
  const [catalog, setCatalog] = useState<Catalog | null>(null)
  const [progress, setProgress] = useState<Progress | null>(null)
  const [paths, setPaths] = useState<Path[]>([])
  const [tasks, setTasks] = useState<Task[]>([])
  const [sessions, setSessions] = useState<Session[]>([])
  const [history, setHistory] = useState<{ id: number; rows: Message[] } | null>(null)
  const [resources, setResources] = useState<Resource[]>([])
  const [assignments, setAssignments] = useState<Assignment[]>([])
  const [submissions, setSubmissions] = useState<Submission[]>([])
  const [jobs, setJobs] = useState<Job[]>([])
  const [preview, setPreview] = useState<{ action: AIAction; data: Preview } | null>(null)
  const [pathId, setPathId] = useState<number | null>(null)
  const [minutes, setMinutes] = useState<number | null>(null)
  const [goal, setGoal] = useState<string | null>(null)
  const [source, setSource] = useState<InterviewSource | null>(null)
  const [mode, setMode] = useState('socratic')
  const [input, setInput] = useState('')
  const [kind, setKind] = useState<keyof typeof kinds>('text')
  const [answer, setAnswer] = useState('')
  const [address, setAddress] = useState('')
  const [choices, setChoices] = useState<Record<string,string>>({})
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [tick, refresh] = useState(0)
  const submissionKey = useRef<string | null>(null)
  const selected = catalog?.topics.find((item) => item.id === topic)
  const assignment = assignments.find((item) => item.id === topic)
  const visiblePaths = tab === 'path' && reportId ? paths.filter((row) => row.data.source?.report_id === reportId) : paths
  const path = visiblePaths.find((row) => row.id === pathId) ?? visiblePaths[0]
  const currentSource = source?.report_id === reportId ? source : null
  const budget = minutes ?? paths[0]?.data.weekly_minutes ?? progress?.diagnosis.suggested_minutes ?? 140
  const objective = goal ?? paths[0]?.data.goal ?? ''
  const activeJob = jobs.find((row) => ['queued', 'running'].includes(row.state))
  const failed = jobs[0]?.state === 'failed' ? jobs[0] : null
  const assessment = progress?.assessments.find((item) => item.id === assessmentId)
  const latestAssessment = progress?.assessments.find((item) => item.result)
  const session = sessions.find((row) => row.id === sessionId)
  const title = (key: string) => catalog?.topics.find((item) => item.id === key)?.title ?? key
  const nextTopic = path?.data.modules.find((item) => !tasks.some((task) => task.topic === item.id && task.status === 'completed'))
  const activeDay = dateKey()

  useEffect(() => {
    if (!reportId || tab !== 'path') return
    let ignore = false
    learning.interviewSource(reportId).then((data) => { if (!ignore) setSource(data) })
      .catch((err) => { if (!ignore) setError(errorMessage(err)) })
    return () => { ignore = true }
  }, [tab, reportId])

  useEffect(() => {
    let ignore = false
    Promise.all([learning.catalog(), learning.assignments()]).then(([value, library]) => {
      if (!ignore) { setCatalog(value); setAssignments(library) }
    }).catch((err) => { if (!ignore) setError(errorMessage(err)) })
    return () => { ignore = true }
  }, [])

  useEffect(() => {
    let ignore = false
    async function load() {
      if (tab === 'daily' || tab === 'home') {
        const today = await learning.daily(activeDay)
        if (!ignore) setTasks(today.tasks)
      }
      const [report, roadmaps, queue] = await Promise.all([learning.progress(), learning.paths(), learning.jobs()])
      if (ignore) return
      setProgress(report); setPaths(roadmaps); setJobs(queue)
      if (tab === 'mentor') {
        const saved = await learning.sessions()
        if (!ignore) setSessions(saved)
        if (sessionId) {
          const current = await learning.messages(sessionId)
          if (!ignore) setHistory({ id: sessionId, rows: current.messages })
        }
      }
      if (tab === 'resources' || tab === 'mentor' || tab === 'daily') {
        const material = await learning.resources(topic)
        if (!ignore) setResources(material)
      }
      if (tab === 'assignment') {
        const versions = await learning.submissions(topic)
        if (!ignore) setSubmissions(versions)
      }
    }
    void load().catch((err) => { if (!ignore) setError(errorMessage(err)) })
    return () => { ignore = true }
  }, [tab, topic, sessionId, tick, activeDay])

  useEffect(() => {
    if (!activeJob) return
    const timeout = window.setTimeout(() => refresh((x) => x + 1), 1300)
    return () => window.clearTimeout(timeout)
  }, [activeJob, tick])

  function go(next: Tab, value = topic, extra: Record<string,string> = {}) {
    setParams({ tab: next, topic: value, ...extra })
    setPreview(null); setError(''); setInput(''); setChoices({}); setSubmissions([])
    if (value !== topic) { setAnswer(''); setAddress(''); submissionKey.current = null; setResources([]) }
  }

  async function act(action: () => Promise<void>, reload = true) {
    setBusy(true); setError('')
    try { await action(); if (reload) refresh((x) => x + 1) }
    catch (err) { setError(errorMessage(err)) }
    finally { setBusy(false) }
  }

  function review(action: AIAction) {
    void act(async () => setPreview({ action, data: await learning.preview(action) }), false)
  }

  function topicPicker() {
    return <label>知识点<select value={topic} onChange={(event) => go(tab, event.target.value)}>
      {catalog?.topics.map((item) => <option key={item.id} value={item.id}>{item.title}</option>)}
    </select></label>
  }

  return <div className="career-page">
    <section className="hero"><h1>成长中心</h1><p>根据目标岗位和已有证据安排学习，用作业和测评检验理解。</p></section>
    <nav className="career-tabs" aria-label="成长中心分区">{Object.entries(tabs).map(([key, label]) =>
      <button className="button button-outline" aria-pressed={tab === key} key={key} onClick={() => go(key as Tab)}>{label}</button>)}</nav>
    {error && <Feedback kind="error">{error}</Feedback>}
    {activeJob && <p className="job-status" role="status">AI 任务处理中…</p>}
    {failed && <div className="form-error" role="alert"><p>{messages[failed.error as keyof typeof messages] ?? '学习任务处理失败'}（{failed.error}）</p>
      <button className="button button-outline" disabled={busy || !!activeJob || failed.attempt >= 3 ||
        ['MODEL_CONFIG_CHANGED','LEARNING_PREVIEW_CHANGED'].includes(failed.error ?? '')}
        onClick={() => void act(async () => { await learning.retry(failed.id) })}>重试最近任务</button>
    </div>}
    {preview && <section className="surface detail-panel grid gap-3">
      <h2>核对发送内容</h2><p>模型服务 · {preview.data.model_host}</p>
      <pre className="max-h-64 overflow-auto whitespace-pre-wrap break-all text-xs">{JSON.stringify(preview.data.payload, null, 2)}</pre>
      <div className="career-actions">
        <button className="button button-filled" disabled={busy || !!activeJob} onClick={() => void act(async () => {
          await learning.approve(preview.action, preview.data.approval); setPreview(null); setInput('')
        })}>同意发送并执行</button>
        <button className="button button-outline" onClick={() => setPreview(null)}>取消</button>
      </div>
    </section>}
    {tab === 'home' && progress && <section className="surface detail-panel grid gap-3">
      <h2>{progress.diagnosis.target}</h2>
      <p>当前学习阶段 · {nextTopic?.title ?? (path ? '计划中的知识点均已安排' : '准备路线')}</p>
      <p>任务完成率 {progress.completion_rate}% · 已通过测评 {progress.diagnosis.summary.verified} 项</p>
      <p>今日任务 · {tasks.length ? tasks.map((item) => `${item.data.title}（${item.data.minutes} 分钟）`).join('、') : '暂无安排'}</p>
      <p>最近测评 · {latestAssessment ? `${title(latestAssessment.topic)} · ${latestAssessment.result?.score} 分` : '暂无记录'}</p>
      <div className="career-actions"><button className="button button-filled" onClick={() => go(path ? 'daily' : 'path')}>
        {path ? '查看今日任务' : '制定学习路线'}</button></div>
    </section>}
    {tab === 'diagnosis' && progress && <DiagnosisPanel data={progress.diagnosis} />}
    {tab === 'path' && <>
      <section className="surface detail-panel"><h2>路线设置</h2>
        {currentSource && <p>本次面试 · {currentSource.target} · 薄弱项 {currentSource.weaknesses.join('、') || '暂无记录'}</p>}
        <form className="account-form" onSubmit={(event) => { event.preventDefault(); void act(async () => {
          await learning.path(budget, objective.trim(), undefined, reportId ?? undefined); setPathId(null)
        }) }}>
          <label>每周可投入（分钟）<input required type="number" min={15} max={1200} value={budget}
            onChange={(event) => setMinutes(Number(event.target.value))} /></label>
          <label>学习目标或兴趣<input maxLength={200} placeholder="例如用 Python 做岗位数据分析" value={objective}
            onChange={(event) => setGoal(event.target.value)} /></label>
          <button className="button button-filled" disabled={busy || Boolean(reportId && !currentSource)}>
            {reportId ? '根据本次面试生成路线' : paths.length ? '按新目标调整路线' : '生成学习路线'}</button>
        </form>
      </section>
      {path && <section className="surface detail-panel grid gap-3">
        <label>路线版本<select value={path.id} onChange={(event) => setPathId(Number(event.target.value))}>
          {visiblePaths.map((row) => <option key={row.id} value={row.id}>第 {row.version} 版</option>)}
        </select></label>
        <h2>{path.data.target} · 每周 {path.data.weekly_minutes} 分钟</h2>
        <p>{path.data.reason} · 预计 {path.data.estimated_weeks} 周 · 已通过测评 {path.data.verified.length} 项</p>
        {path.data.source && <p>来源 <Link className="application-link"
          to={`/interview-practice?tab=report&session=${path.data.source.session_id}`}>面试报告 #{path.data.source.report_id}</Link>
          {path.data.source.weaknesses.length > 0 && ` · ${path.data.source.weaknesses.join('、')}`}</p>}
        <ol className="grid gap-2">{path.data.modules.map((row, index) => <li key={row.id} className="career-detail">
          <h3>{index + 1}. {row.title} · {row.minutes} 分钟</h3>
          <p>先修 · {row.requires.map(title).join('、') || '无'}</p><p>{row.reason}</p>
          <p>实践 · {row.exercise}</p><p>验收 · {row.acceptance}</p>
        </li>)}</ol>
        <button className="button button-outline" disabled={busy || !!activeJob}
          onClick={() => review({ kind: 'path', record_id: path.id })}>预览 AI 路线讲解</button>
        {path.data.mentor && <LessonPanel data={path.data.mentor} />}
      </section>}
    </>}
    {tab === 'daily' && <section className="surface detail-panel grid gap-3">
      <h2>今日安排 · {activeDay}</h2>
      {!tasks.length && <Feedback kind="empty">当前暂无任务。可先生成路线，或在本周预算内补充任务。</Feedback>}
      {tasks.map((item) => <TaskPanel key={item.id} task={item} busy={busy}
        change={(status, actual) => void act(async () => { await learning.task(item.id, status, actual) })}
        teach={() => go('mentor', item.topic)} />)}
      {path && <form className="account-form" onSubmit={(event) => { event.preventDefault()
        const form = new FormData(event.currentTarget)
        void act(async () => { await learning.addTask(topic, Number(form.get('minutes')), activeDay) })
      }}>
        {topicPicker()}
        <label>补充任务预计分钟<input required type="number" min={1} max={120} defaultValue={15} name="minutes" /></label>
        <button className="button button-outline" disabled={busy}>追加任务</button>
      </form>}
    </section>}
    {tab === 'mentor' && <>
      <section className="surface detail-panel account-form">
        <h2>AI 导师</h2>
        {topicPicker()}
        <label>教学模式<select value={mode} onChange={(event) => setMode(event.target.value)}>
          {Object.entries(catalog?.modes ?? {}).map(([key,label]) => <option key={key} value={key}>{label}</option>)}
        </select></label>
        <button className="button button-filled" disabled={busy || !selected} onClick={() => void act(async () => {
          const saved = await learning.createSession(topic, mode); go('mentor', topic, { session: String(saved.id) })
        })}>新建教学会话</button>
        {!!sessions.length && <label>继续历史会话<select value={sessionId ?? ''} onChange={(event) => {
          const saved = sessions.find((row) => row.id === Number(event.target.value))
          if (saved) go('mentor', saved.topic, { session: String(saved.id) })
        }}>
          <option value="">选择会话</option>
          {sessions.map((row) => <option value={row.id} key={row.id}>#{row.id} · {title(row.topic)} · {catalog?.modes[row.mode]}</option>)}
        </select></label>}
        <div><button className="button button-outline" onClick={() => go('resources', topic)}>查看相关学习资料</button></div>
      </section>
      {session && <section className="surface detail-panel grid gap-3">
        <h2>{title(session.topic)} · {catalog?.modes[session.mode]}</h2>
        {history?.id === sessionId && history.rows.map((row) => <article className="career-detail" key={row.id}>
          <h3>{row.role === 'mentor' ? '导师' : '我的回答'}</h3><LessonPanel data={row.data} />
          {row.role === 'mentor' && <button className="button button-outline" disabled={busy} onClick={() => void act(async () => {
            await learning.resource({ topic: session.topic, title: title(session.topic) + ' · 导师笔记', kind: 'note',
              text: [row.data.explanation, row.data.example, row.data.next_step].filter(Boolean).join('\n\n') })
            go('resources', session.topic)
          })}>保存为学习笔记</button>}
        </article>)}
        <form className="account-form" onSubmit={(event) => { event.preventDefault()
          review({ kind: 'lesson', record_id: session.id, message: input.trim() })
        }}>
          <label>给导师的话<textarea required maxLength={3000} value={input} placeholder="先说说你已经理解的部分"
            onChange={(event) => setInput(event.target.value)} /></label>
          <button className="button button-filled" disabled={busy || !!activeJob || !input.trim()}>预览教学对话</button>
        </form>
      </section>}
    </>}
    {tab === 'resources' && <section className="surface detail-panel grid gap-3">
      <h2>学习资料</h2>
      <div className="account-form">{topicPicker()}</div>
      {resources.map((row, index) => <article className="career-detail" key={row.id ?? 'catalog-' + index}>
        <h3>{row.title}</h3><p>{row.source} · {row.credibility}</p>
        {row.url && <a className="text-brand underline" href={row.url} target="_blank" rel="noreferrer">打开资料</a>}
        {row.text && <details><summary>查看内容</summary><p className="whitespace-pre-wrap">{row.text}</p></details>}
      </article>)}
      <form className="account-form" onSubmit={(event) => { event.preventDefault()
        const element = event.currentTarget; const form = new FormData(element)
        void act(async () => {
          const file = form.get('file')
          if (file instanceof File && file.size) {
            const upload = new FormData()
            upload.set('topic', topic); upload.set('title', String(form.get('title'))); upload.set('file', file)
            await learning.upload('/resources/upload', upload)
          } else await learning.resource({ topic, title: form.get('title'), kind: form.get('kind'),
            url: form.get('url') || null, text: form.get('text') })
          element.reset()
        })
      }}>
        <label>资料标题<input name="title" maxLength={150} required /></label>
        <label>资料类型<select name="kind"><option value="note">学习笔记</option><option value="official">官方资料</option>
          <option value="tutorial">教程</option><option value="video">视频课程链接</option><option value="project">项目文档</option></select></label>
        <label>资料网址<input name="url" type="url" /></label>
        <label>资料内容<textarea name="text" maxLength={8000} /></label>
        <label>上传资料（TXT、Markdown 或 DOCX）<input type="file" name="file" accept=".txt,.md,.docx" /></label>
        <button className="button button-filled" disabled={busy}>保存资料</button>
      </form>
    </section>}
    {tab === 'assignment' && <section className="surface detail-panel grid gap-3">
      <h2>实践作业</h2>
      <form className="account-form" onSubmit={(event) => {
        event.preventDefault()
        const element = event.currentTarget; const form = new FormData(element)
        const file = form.get('file')
        void act(async () => {
          submissionKey.current ??= crypto.randomUUID()
          if (file instanceof File && file.size) {
            const upload = new FormData()
            upload.set('request_id', submissionKey.current); upload.set('file', file)
            await learning.upload('/assignments/' + topic + '/upload', upload)
          } else {
            const samples = Object.keys(assignment?.fixtures ?? {})
              .map((key) => [key, String(form.get('fixture-' + key) ?? '')] as const)
              .filter(([, value]) => value !== '')
            await learning.submit(topic, { request_id: submissionKey.current, kind, content: answer,
              repository_url: kind === 'github' ? address : undefined,
              ...(samples.length ? { sample_outputs: Object.fromEntries(samples.map(([key, value]) => [key, Number(value)])) } : {}) })
          }
          setAnswer(''); setAddress(''); submissionKey.current = null; element.reset()
        })
      }}>
        {topicPicker()}
        {assignment && <><p>目标 · {assignment.title}</p><p>实践 · {assignment.exercise}</p><p>验收 · {assignment.acceptance}</p>
          <p>提交方式 · {assignment.submission}</p></>}
        <button type="button" className="button button-outline" onClick={() => go('resources', topic)}>查看作业资料</button>
        <label>作业类型<select value={kind} onChange={(event) => {
          setKind(event.target.value as keyof typeof kinds); submissionKey.current = null
        }}>{Object.entries(kinds).map(([key,label]) => <option key={key} value={key}>{label}</option>)}</select></label>
        <p>评分项 · {assignment?.rubrics[kind]?.join('、')}</p>
        <label>提交内容<textarea maxLength={12000} rows={7} value={answer}
          onChange={(event) => { setAnswer(event.target.value); submissionKey.current = null }} /></label>
        {Object.keys(assignment?.fixtures ?? {}).length > 0 && <details className="career-detail">
          <summary>核对固定样例（选填）</summary>
          {Object.entries(assignment?.fixtures ?? {}).map(([key, label]) => <label key={key}>{label}
            <input name={'fixture-' + key} type="number" step={1} onChange={() => { submissionKey.current = null }} />
          </label>)}
        </details>}
        {kind === 'github' && <label>公开仓库链接<input type="url" required value={address}
          onChange={(event) => { setAddress(event.target.value); submissionKey.current = null }} /></label>}
        <label>上传作业（TXT、Markdown 或 DOCX）<input type="file" name="file" accept=".txt,.md,.docx"
          onChange={() => { submissionKey.current = null }} /></label>
        <button className="button button-filled" disabled={busy}>保存作业版本</button>
      </form>
      {submissions.map((row) => <article className="career-detail grid gap-2" key={row.id}>
        <h3>第 {row.version} 版 · {states[row.status]}</h3>
        <details><summary>提交内容</summary><pre className="overflow-auto whitespace-pre-wrap">{row.data.content || row.data.repository_url}</pre></details>
        {row.evaluation ? <FeedbackPanel item={row.evaluation} /> : <button className="button button-outline" disabled={busy || !!activeJob}
          onClick={() => review({ kind: 'evaluation', record_id: row.id })}>预览 AI 作业评估</button>}
      </article>)}
    </section>}
    {tab === 'exam' && <section className="surface detail-panel grid gap-3">
      <h2>阶段测评</h2>
      <div className="account-form">{topicPicker()}
        <button className="button button-filled" disabled={busy || !selected} onClick={() => void act(async () => {
          const created = await learning.exam(topic)
          go('exam', topic, { assessment: String(created.id) })
        })}>开始或恢复测评</button>
      </div>
      {assessment && <form className="account-form" onSubmit={(event) => { event.preventDefault()
        void act(async () => { await learning.finishExam(assessment.id, choices) })
      }}>
        <h3>{title(assessment.topic)}</h3>
        {assessment.questions.map((row) => <fieldset key={row.id} className="career-detail">
          <legend>{row.question}</legend>
          {row.choices.map((value, i) => <label className="block py-1" key={value}>
            <input type="radio" name={'exam-' + row.id} required disabled={!!assessment.result}
              checked={choices[row.id] === String(i)} onChange={() => setChoices((old) => ({ ...old, [row.id]: String(i) }))} /> {value}
          </label>)}
          {assessment.result?.checked.filter((item) => item.id === row.id).map((item) => <p key={item.id}>
            {item.correct ? '正确' : '待复练'} · 正确选项 {item.answer}</p>)}
        </fieldset>)}
        {assessment.result ? <p>测评结果 · {assessment.result.score} 分 · {
          ({ first: '首次测评', reassessment: '不同题复测', practice: '重复练习' })[assessment.result.mode]}</p> :
          <button className="button button-filled" disabled={busy}>提交测评</button>}
      </form>}
      {assessment?.result && <article className="career-detail">
        <h3>开放实践 · {assessment.application.type}</h3>
        <p>{assessment.application.question}</p><p>验收 · {assessment.application.acceptance}</p>
        <button className="button button-outline" onClick={() => go('assignment', assessment.topic)}>在作业中心提交开放实践</button>
      </article>}
      {(progress?.assessments ?? []).map((item) => <button key={item.id} className="button button-outline"
        onClick={() => go('exam', item.topic, { assessment: String(item.id) })}>
        #{item.id} · {title(item.topic)} · {item.result ? item.result.score + ' 分' : '继续答题'}</button>)}
    </section>}
    {tab === 'report' && progress && <>
      <section className="surface detail-panel grid gap-3">
        <h2>成长报告</h2>
        <p>学习时长 {progress.minutes} 分钟 · 任务完成 {progress.completed} / {progress.total} · 完成率 {progress.completion_rate}%</p>
        <p>作业提交 {progress.submissions} 次 · 测评记录 {progress.assessments.filter((item) => item.result).length} 条</p>
        <h3>近期能力变化</h3>
        {!progress.history.length && <p>通过测评后，这里会记录能力变化。</p>}
        <ol>{progress.history.map((row) => <li key={row.id}>
          {title(row.topic)} · {masteryLabels[row.data.prior]} → {masteryLabels[row.data.status]} · {row.data.score} 分 · {row.data.reason}
        </li>)}</ol>
        <h3>下一阶段建议</h3>
        <p>{nextTopic ? `${nextTopic.title} · ${nextTopic.exercise}` : '可以安排一次新的学习路线或复测。'}</p>
      </section>
      <DiagnosisPanel data={progress.diagnosis} />
    </>}
  </div>
}

