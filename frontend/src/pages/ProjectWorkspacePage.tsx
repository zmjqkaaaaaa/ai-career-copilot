import { useEffect, useMemo, useState } from 'react'
import { Link, useSearchParams } from 'react-router'
import { ArchitectureIndex, EvidenceList, FileTree, LessonCard } from '../components/mentor/CodeEvidence'
import { errorMessage } from '../services/api'
import { mentor, type Architecture, type CodeFile, type Content, type Detail, type Evidence,
  type Lesson, type Mastery, type Preview, type Project, type Quiz, type Study } from '../services/codeProjects'

const tabs = { overview: '架构概览', code: '代码阅读', knowledge: '知识库', chat: 'AI 导师', quiz: '理解测试', mastery: '掌握报告' }
const dimensions = { overview: '项目整体理解', stack: '技术栈理解', structure: '文件结构理解',
  functions: '核心函数理解', api: 'API 流程理解', database: '数据库理解', ai: 'AI 模块理解', debug: 'Debug 能力', extension: '修改和扩展能力' }
const modes = { concept: '基础概念', function: '函数理解', flow: '执行流程', choice: '技术选型',
  debug: 'Debug 分析', architecture: '架构理解', change: '修改方案' }
const statuses: Record<string, string> = { untested: '待测试', practiced: '有书面练习记录', verified_in_quiz: '已通过本维度测验', needs_practice: '待巩固' }
const judgments: Record<string, string> = { correct: '正确', partial: '部分正确', missing: '缺失', incorrect: '错误' }
const examples = { code: '代码中这个分支为什么需要提前返回？', chat: '请选择一个已经读过的函数，说明输入和返回值。' }

type Overview = { project: number; commit: string; files: CodeFile[]; architecture: Architecture; lessons: Lesson[];
  history: Lesson[]; quizzes: Quiz[]; mastery: Mastery }

export function ProjectWorkspacePage() {
  const [params, setParams] = useSearchParams()
  const projectId = Number(params.get('project')) || null
  const requestedPlan = Number(params.get('recommendation')) || null
  const [plan, setPlan] = useState<{ id: number; name: string } | null>(null)
  const [projects, setProjects] = useState<Project[]>([])
  const [details, setDetails] = useState<Detail | null>(null)
  const [storedView, setView] = useState<Overview | null>(null)
  const [url, setUrl] = useState('')
  const [tab, setTab] = useState<keyof typeof tabs>('overview')
  const [fileId, setFileId] = useState<number | null>(null)
  const [file, setFile] = useState<Content | null>(null)
  const [symbol, setSymbol] = useState('')
  const [question, setQuestion] = useState('')
  const [query, setQuery] = useState('')
  const [matches, setMatches] = useState<Evidence[] | null>(null)
  const [dimension, setDimension] = useState('functions')
  const [mode, setMode] = useState('function')
  const [quizId, setQuizId] = useState<number | null>(null)
  const [answer, setAnswer] = useState('')
  const [selfNote, setSelfNote] = useState('')
  const [confirmRemove, setConfirmRemove] = useState(false)
  const [preview, setPreview] = useState<{ info: Preview; body: Study; project: number } | null>(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [tick, setTick] = useState(0)
  const update = () => setTick((value) => value + 1)
  const current = details?.id === projectId ? details : null
  const planId = requestedPlan ?? current?.recommendation_id
  const selectedVersion = params.get('commit')
  const commit = current ? current.versions.find((item) => item.sha === selectedVersion)?.sha ?? current.active_commit : null
  const view = storedView?.project === projectId && storedView.commit === commit ? storedView : null
  const pending = current?.tasks.find((task) => task.state === 'queued' || task.state === 'running')
  const failed = current?.tasks[0]?.state === 'failed' ? current.tasks[0] : null
  const blocked = busy || Boolean(pending)
  const code = file?.id === fileId && view?.files.some((item) => item.id === fileId) ? file : null
  const quiz = view?.quizzes.find((item) => item.id === quizId) ?? view?.quizzes[0]
  const feedback = view?.mastery.attempts.find((item) => item.quiz_id === quiz?.id)
  const github = current && commit ? `${current.url}/blob/${commit}` : ''
  const lines = useMemo(() => code?.content?.split('\n') ?? [], [code?.content])

  useEffect(() => {
    if (!planId) return
    let ignore = false
    mentor.recommendation(planId).then((value) => { if (!ignore) setPlan(value) })
      .catch((e) => { if (!ignore && requestedPlan) setError(errorMessage(e)) })
    return () => { ignore = true }
  }, [planId, requestedPlan])

  useEffect(() => {
    let ignore = false
    mentor.list().then((items) => { if (!ignore) setProjects(items) })
      .catch((e) => { if (!ignore) setError(errorMessage(e)) })
    if (projectId) {
      mentor.detail(projectId).then((item) => { if (!ignore) setDetails(item) })
        .catch((e) => { if (!ignore) setError(errorMessage(e)) })
    }
    return () => { ignore = true }
  }, [projectId, tick])

  useEffect(() => {
    if (!pending) return
    const timer = window.setTimeout(() => setTick((value) => value + 1), 1300)
    return () => window.clearTimeout(timer)
  }, [pending, tick])

  useEffect(() => {
    if (!projectId || !commit) return
    let ignore = false
    Promise.all([mentor.files(projectId, commit), mentor.architecture(projectId, commit),
      mentor.explanations(projectId, commit), mentor.history(projectId, commit),
      mentor.quizzes(projectId, commit), mentor.mastery(projectId, commit)])
      .then(([files, architecture, lessons, history, quizzes, mastery]) => {
        if (!ignore) setView({ project: projectId, commit, files, architecture, lessons, history, quizzes, mastery })
      }).catch((e) => { if (!ignore) setError(errorMessage(e)) })
    return () => { ignore = true }
  }, [projectId, commit, tick])

  useEffect(() => {
    if (!projectId || !commit || !fileId || !view?.files.some((item) => item.id === fileId)) return
    let ignore = false
    mentor.file(projectId, commit, fileId).then((item) => { if (!ignore) setFile(item) })
      .catch((e) => { if (!ignore) setError(errorMessage(e)) })
    return () => { ignore = true }
  }, [projectId, commit, fileId, tick, view])

  function select(id: number, version?: string) {
    setParams(version ? { project: String(id), commit: version } : { project: String(id) })
    setView(null); setFileId(null); setFile(null); setSymbol(''); setMatches(null); setAnswer('')
    setQuizId(null); setConfirmRemove(false); setPreview(null); setError(''); setQuestion(''); setSelfNote('')
  }

  async function act(action: () => Promise<void>, reload = true) {
    setBusy(true); setError('')
    try { await action(); if (reload) update() }
    catch (e) { setError(errorMessage(e)) }
    finally { setBusy(false) }
  }

  function review(input: Omit<Study, 'commit'>) {
    if (!projectId || !commit) return
    const body = { ...input, commit }
    void act(async () => setPreview({ info: await mentor.preview(projectId, body), body, project: projectId }), false)
  }

  function changeTab(next: keyof typeof tabs) {
    setPreview(null)
    setTab(next)
  }

  return <div className="career-page">
    <section className="hero"><h1>项目工作台</h1><p>导入一个公开 GitHub 仓库，读懂真实代码，再用答题检验理解。</p></section>
    <div className="career-columns">
      <aside className="surface detail-panel">
        <h2>我的项目</h2>
        <form className="account-form" onSubmit={(e) => {
          e.preventDefault()
          void act(async () => { const imported = await mentor.create(url.trim(), requestedPlan ?? undefined); select(imported.project.id); setTab('overview'); setUrl('') })
        }}>
          <label>公开 GitHub 仓库地址<input type="url" placeholder="https://github.com/owner/repository"
            required maxLength={240} value={url} onChange={(e) => setUrl(e.target.value)} /></label>
          {requestedPlan && plan?.id === requestedPlan && <p>关联方案 · {plan.name}</p>}
          <button className="button button-filled" disabled={busy || !url.trim()}>导入仓库</button>
        </form>
        <ul className="career-files-list">{projects.map((row) => <li key={row.id}>
          <button aria-pressed={projectId === row.id} onClick={() => { select(row.id); setTab('overview') }}>
            {row.slug} {row.active_commit ? '' : '· 待导入'}
          </button></li>)}
        </ul>
      </aside>
      <div className="career-main">
        {error && <p className="form-error" role="alert">{error}</p>}
        {!current && <section className="surface detail-panel"><h2>{projectId ? '正在读取项目…' : '请导入或选择一个项目'}</h2></section>}
        {current && <section className="surface detail-panel account-form">
          <h2 className="break-all">{current.slug}</h2>
          {plan && plan.id === current.recommendation_id && <p>已关联方案 · {plan.name}</p>}
          {current.metadata.description && <p>{current.metadata.description}</p>}
          {current.active_commit && <p>{current.metadata.language || '语言待识别'} · {current.metadata.default_branch} · {current.metadata.stargazers_count ?? 0} Stars</p>}
          <a href={current.url} target="_blank" rel="noreferrer" className="text-brand underline">打开公开仓库</a>
          {!!current.versions.length && <label>仓库版本<select value={commit ?? ''} onChange={(e) => select(current.id, e.target.value)}>
            {current.versions.map((item) => <option value={item.sha} key={item.sha}>{item.sha.slice(0, 10)}{item.sha === current.active_commit ? ' · 最新导入' : ' · 历史版本'}</option>)}
          </select></label>}
          {commit && <Link className="button button-outline"
            to={`/interview-practice?repository=${current.id}&commit=${commit}`}>使用此版本练习项目面试</Link>}
          <div className="career-actions">
            <button className="button button-outline" disabled={blocked} onClick={() => void act(async () => {
              await mentor.refresh(current.id); setParams({ project: String(current.id) })
            })}>检查仓库更新</button>
            <button className="button button-outline" disabled={blocked} onClick={() => setConfirmRemove((value) => !value)}>{confirmRemove ? '取消删除' : '移除本地项目'}</button>
            {confirmRemove && <button className="button button-outline" disabled={blocked} onClick={() => void act(async () => {
              await mentor.remove(current.id); setParams({}); setView(null); setConfirmRemove(false)
            })}>确认移除本地项目和学习记录</button>}
          </div>
          {pending && <p role="status">任务{pending.state === 'queued' ? '已排队' : '处理中'}…</p>}
          {failed && <div className="form-error" role="alert">
            <p>{failed.error_message}（{failed.error_code}）</p>
            {failed.retry_at && <p>预计恢复 · {new Date(failed.retry_at * 1000).toLocaleString()}</p>}
            {failed.attempt < 3 && !['MODEL_CONFIG_CHANGED', 'CODE_PREVIEW_CHANGED'].includes(failed.error_code ?? '') &&
              <button className="button button-outline" disabled={blocked} onClick={() => void act(async () => { await mentor.retry(current.id, failed.id) })}>重试最近任务</button>}
          </div>}
        </section>}
        {current && commit && view && <>
          <nav aria-label="项目工作台分区" className="career-tabs">
            {(Object.keys(tabs) as (keyof typeof tabs)[]).map((key) =>
              <button className="button button-outline" key={key} aria-pressed={tab === key} onClick={() => changeTab(key)}>{tabs[key]}</button>)}
          </nav>
          {preview?.project === current.id && preview.body.commit === commit && <section className="surface detail-panel grid gap-3">
            <h2>核对发送内容</h2><p>模型服务 · {preview.info.model_host}</p>
            <pre className="max-h-72 overflow-auto whitespace-pre-wrap break-all text-xs">{JSON.stringify(preview.info.payload, null, 2)}</pre>
            <div className="career-actions">
              <button className="button button-filled" disabled={blocked} onClick={() => void act(async () => {
                await mentor.send(current.id, preview.body, preview.info.approval)
                if (preview.body.kind === 'grade') setAnswer('')
                if (preview.body.kind === 'chat') setQuestion('')
                setPreview(null)
              })}>同意发送并执行</button>
              <button className="button button-outline" onClick={() => setPreview(null)}>取消</button>
            </div>
          </section>}
          {tab === 'overview' && <>
            <ArchitectureIndex value={view.architecture} github={github} />
            <section className="surface detail-panel">
              <h2>架构分析与数据流</h2>
              <button className="button button-filled mt-2" disabled={blocked || !view.architecture.files_read} onClick={() => review({ kind: 'analyze' })}>
                预览架构分析</button>
            </section>
            {view.architecture.analysis && <LessonCard lesson={view.architecture.analysis} github={github} />}
          </>}
          {tab === 'code' && <>
            <section className="surface detail-panel"><h2>文件树</h2>
              <FileTree files={view.files} active={fileId} onSelect={(id) => { setFileId(id); setSymbol(''); setPreview(null) }} />
            </section>
            {code && <section className="surface detail-panel account-form">
              <h2 className="break-all">{code.path}</h2><p>{code.language} · {code.size} 字节 · {code.kind}</p>
              {!code.loaded && <button className="button button-outline" disabled={blocked || !code.readable}
                onClick={() => void act(async () => { await mentor.load(current.id, commit, code.id) })}>读取这个文件</button>}
              {code.loaded && <>
                <pre aria-label="带行号的源代码" className="max-h-96 overflow-auto rounded-lg border border-line bg-slate-50 p-3 text-xs">
                  {lines.map((line, index) => <div key={index}><span className="mr-3 inline-block min-w-9 select-none text-right text-muted">{index + 1}</span>{line}</div>)}
                </pre>
                <label>选择函数或类<select value={symbol} onChange={(e) => setSymbol(e.target.value)}>
                  <option value="">整个文件</option>
                  {code.index?.symbols.map((item) => <option value={item.name} key={item.name + ':' + item.start}>{item.name} · {item.start}–{item.end}</option>)}
                </select></label>
                <button className="button button-filled" disabled={blocked}
                  onClick={() => review({ kind: 'explain', file_id: code.id, ...(symbol && { symbol }) })}>预览代码解释</button>
              </>}
            </section>}
            {view.lessons.map((lesson) => <LessonCard key={lesson.id} lesson={lesson} github={github} />)}
          </>}
          {tab === 'knowledge' && <>
            <section className="surface detail-panel">
              <form className="account-form" onSubmit={(e) => { e.preventDefault(); void act(async () => {
                setMatches((await mentor.knowledge(current.id, commit, query.trim())).matches)
              }, false) }}>
                <label>搜索文件、函数或模块<input value={query} maxLength={350} onChange={(e) => setQuery(e.target.value)} /></label>
                <button className="button button-filled" disabled={busy}>搜索当前版本</button>
              </form>
              {matches && (matches.length ? <EvidenceList evidence={matches} github={github} /> : <p>已读代码中暂无匹配项。</p>)}
            </section>
            <ArchitectureIndex value={view.architecture} github={github} />
          </>}
          {tab === 'chat' && <>
            <section className="surface detail-panel"><h2>AI Coding 导师</h2>
              <form className="account-form" onSubmit={(e) => { e.preventDefault(); review({
                kind: 'chat', question: question.trim(), ...(code && code.loaded && { file_id: code.id }) }) }}>
                {code?.loaded && <p>当前参考文件 · {code.path}</p>}
                <label>我的问题<textarea required maxLength={1600} placeholder={examples.chat} value={question} onChange={(e) => setQuestion(e.target.value)} /></label>
                <button className="button button-filled" disabled={blocked || !question.trim()}>预览导师提问</button>
              </form>
            </section>
            {view.history.map((lesson) => <LessonCard key={lesson.id} lesson={lesson} github={github} />)}
          </>}
          {tab === 'quiz' && <>
            <section className="surface detail-panel account-form"><h2>代码理解测试</h2>
              <label>能力维度<select value={dimension} onChange={(e) => setDimension(e.target.value)}>
                {Object.entries(dimensions).map(([key, label]) => <option value={key} key={key}>{label}</option>)}</select></label>
              <label>题型<select value={mode} onChange={(e) => setMode(e.target.value)}>
                {Object.entries(modes).map(([key, label]) => <option value={key} key={key}>{label}</option>)}</select></label>
              <button className="button button-filled" disabled={blocked} onClick={() => review({ kind: 'quiz', dimension, mode,
                ...(code?.loaded && { file_id: code.id }), ...(code?.loaded && symbol && { symbol }) })}>预览生成题目</button>
            </section>
            {quiz && <section className="surface detail-panel account-form">
              <label>选择题目<select value={quiz.id} onChange={(e) => { setQuizId(Number(e.target.value)); setAnswer(''); setPreview(null) }}>
                {view.quizzes.map((item) => <option value={item.id} key={item.id}>#{item.id} · {item.concept}</option>)}</select></label>
              <h3>{quiz.question}</h3>
              <EvidenceList github={github} evidence={quiz.evidence} />
              <form className="account-form" onSubmit={(e) => { e.preventDefault(); review({ kind: 'grade', quiz_id: quiz.id, answer: answer.trim() }) }}>
                <label>我的答案<textarea required maxLength={3500} value={answer} onChange={(e) => setAnswer(e.target.value)} /></label>
                <button className="button button-filled" disabled={blocked || !answer.trim()}>预览提交答案</button>
              </form>
              {feedback && <div className="career-detail">
                <h3>本题得分 · {feedback.score} / 100</h3>
                <p>{feedback.explanation}</p><p>参考答案 · {feedback.expected_answer}</p>
                <ul>{feedback.criteria.map((item, i) => <li key={i}>{item.label} · {judgments[item.result]} · {item.feedback}</li>)}</ul>
                <p>建议练习 · {feedback.practice}</p>
              </div>}
            </section>}
          </>}
          {tab === 'mastery' && <>
            <section className="surface detail-panel"><h2>项目掌握报告</h2>
              <p>通过测验的状态仅针对当前版本和已作答维度。</p>
              <div className="career-grid mt-3">{view.mastery.dimensions.map((item) => <article className="career-detail" key={item.key}>
                <h3>{item.label}</h3><p>{statuses[item.status]}{item.best_score !== null && ` · 最高 ${item.best_score} 分`}</p>
                {item.self_report && <p>用户自述 · {item.self_report}</p>}
                {item.inferred && <p>评估提示 · {item.inferred}</p>}
                <p>下一步 · {item.practice}</p>
              </article>)}</div>
              <form className="account-form mt-3" onSubmit={(e) => { e.preventDefault(); void act(async () => {
                await mentor.selfReport(current.id, commit, dimension, selfNote.trim()); setSelfNote('')
              }) }}>
                <label>自述维度<select value={dimension} onChange={(e) => setDimension(e.target.value)}>
                  {Object.entries(dimensions).map(([key, label]) => <option value={key} key={key}>{label}</option>)}</select></label>
                <label>我的掌握情况<textarea required maxLength={600} value={selfNote} onChange={(e) => setSelfNote(e.target.value)} /></label>
                <button className="button button-outline" disabled={busy || !selfNote.trim()}>保存自述</button>
              </form>
            </section>
            <section className="surface detail-panel"><h2>历史成绩</h2>
              {!view.mastery.attempts.length && <p>当前版本还没有答题记录。</p>}
              <ul>{view.mastery.attempts.map((item) => <li key={item.id}>题目 #{item.quiz_id} · {item.score} / 100 · {item.explanation}</li>)}</ul>
            </section>
          </>}
        </>}
      </div>
    </div>
  </div>
}
