import { useEffect, useRef, useState } from 'react'
import { Link, useSearchParams } from 'react-router'
import { errorMessage } from '../services/api'
import { jobsApi } from '../services/jobs'
import type { Gap, Job, Match, Preview, Requirement, Task, Version } from '../services/jobs'
import { importanceLabels, JobReport } from '../components/jobs/JobReport'

const fields = { position_name: '岗位名称', company_name: '公司名称', location: '工作地点', salary_range: '薪资范围', source_url: '来源链接' } as const
const jobTypes: Record<string, string> = { internship: '实习', full_time: '全职', other: '其他' }
const categories: Record<string, string> = { education: '教育', product: '产品', ai: 'AI 技术', programming: '编程', data: '数据分析', practice: '项目或实习', industry: '行业', communication: '沟通协作' }
const active = (task: Task) => task.state === 'queued' || task.state === 'running'

export function JobMatchingPage() {
  const [params] = useSearchParams()
  const [jobs, setJobs] = useState<Job[]>([])
  const [history, setHistory] = useState<Match[]>([])
  const [versions, setVersions] = useState<Version[]>([])
  const [selection, setSelection] = useState<number | null>(() => Number(params.get('job')) || null)
  const [job, setJob] = useState<Job | null>(null)
  const [requirements, setRequirements] = useState<Requirement[]>([])
  const [assessments, setAssessments] = useState<Record<number, string>>({})
  const [content, setContent] = useState<number | null>(null)
  const [reportId, setReportId] = useState<number | null>(null)
  const [gapData, setGapData] = useState<{ id: number; values: Gap[] } | null>(null)
  const [description, setDescription] = useState('')
  const [version, refresh] = useState(0)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [confirmation, setConfirmation] = useState<(Preview & { path: string }) | null>(null)
  const [deleteId, setDeleteId] = useState<number | null>(null)
  const [tab, setTab] = useState<'positions' | 'history'>('positions')
  const selectionRef = useRef(selection)
  selectionRef.current = selection
  const current = job?.id === selection ? job : null
  const reports = history.filter((item) => item.job_id === selection)
  const report = reports.find((item) => item.id === reportId) ?? reports[0]
  const running = current?.tasks.find(active)
  const latest = current?.tasks[0]
  const paused = busy || Boolean(running)

  useEffect(() => {
    let ignore = false
    Promise.all([jobsApi.list(), jobsApi.history(), jobsApi.versions()]).then(([positions, matches, candidates]) => {
      if (ignore) return
      setJobs(positions); setHistory(matches); setVersions(candidates)
      setContent((prev) => candidates.some((item) => item.id === prev) ? prev : candidates[0]?.id ?? null)
    }).catch((failure) => { if (!ignore) setError(errorMessage(failure)) })
    return () => { ignore = true }
  }, [version])

  useEffect(() => {
    if (!selection) return
    let ignore = false
    jobsApi.detail(selection).then((data) => {
      if (!ignore) { setJob(data); setRequirements(data.requirements) }
    }).catch((failure) => { if (!ignore) setError(errorMessage(failure)) })
    return () => { ignore = true }
  }, [selection, version])

  useEffect(() => {
    if (!report?.id) return
    let ignore = false
    const id = report.id
    jobsApi.gaps(id).then((values) => { if (!ignore) setGapData({ id, values }) })
      .catch((failure) => { if (!ignore) setError(errorMessage(failure)) })
    return () => { ignore = true }
  }, [report?.id])

  useEffect(() => {
    if (!running?.id) return
    const id = running.id
    let stopped = false
    let timer: number
    async function poll() {
      try {
        const task = await jobsApi.task(id)
        if (stopped) return
        if (active(task)) timer = window.setTimeout(poll, 1200)
        else refresh((value) => value + 1)
      } catch (failure) { if (!stopped) setError(errorMessage(failure)) }
    }
    timer = window.setTimeout(poll, 1000)
    return () => { stopped = true; window.clearTimeout(timer) }
  }, [running?.id])

  function select(id: number, match?: number) {
    setSelection(id); setReportId(match ?? null); setAssessments({}); setConfirmation(null); setDeleteId(null); setError('')
  }

  async function act(action: () => Promise<void>, reload = true) {
    setBusy(true); setError('')
    try { await action(); if (reload) refresh((value) => value + 1) }
    catch (failure) { setError(errorMessage(failure)) }
    finally { setBusy(false) }
  }

  function modelPreview(path: string) {
    const requested = selection
    void act(async () => {
      const preview = await jobsApi.preview(path)
      if (selectionRef.current === requested) setConfirmation({ ...preview, path })
    }, false)
  }

  return <div className="career-page">
    <section className="hero"><h1>岗位匹配</h1><p>核对岗位要求，用简历证据判断匹配和准备重点。</p></section>
    {selection !== null && <Link className="text-ai" to={`/application-workspace?tab=positions&job=${selection}`}>在求职执行中查看岗位</Link>}
    <div className="career-tabs" role="group" aria-label="岗位匹配视图">
      <button className="button button-outline" aria-pressed={tab === 'positions'} onClick={() => setTab('positions')}>岗位管理</button>
      <button className="button button-outline" aria-pressed={tab === 'history'} onClick={() => setTab('history')}>历史匹配</button>
    </div>
    {error && <p className="form-error" role="alert">{error}</p>}
    {tab === 'history' ? <section className="surface detail-panel">
      <h2>历史匹配记录</h2>
      {history.length === 0 && <p>还没有匹配报告。</p>}
      <ul className="career-files-list">{history.map((item) => <li key={item.id}>
        <button onClick={() => { select(item.job_id, item.id); setTab('positions') }}>
          {item.position_name} · {item.overall_score ?? '未评分'} · {item.created_at.slice(0, 10)} · 报告 #{item.id}
        </button>
      </li>)}</ul>
    </section> : <div className="career-columns">
      <aside className="surface detail-panel">
        <h2>我的岗位</h2>
        {jobs.length === 0 && <p>还没有岗位。</p>}
        <ul className="career-files-list">{jobs.map((item) => <li key={item.id}>
          <button aria-pressed={selection === item.id} onClick={() => select(item.id)}>{item.position_name}<small>
            {[item.company_name, item.location, item.created_at.slice(0, 10), item.latest_score != null ? `匹配分 ${item.latest_score}` : item.parsed ? '已解析' : '待解析'].filter(Boolean).join(' · ')}
          </small></button>
        </li>)}</ul>
        <button className="button button-outline mt-3" onClick={() => { setSelection(null); setConfirmation(null); setDescription('') }}>录入新岗位</button>
      </aside>
      <div className="career-main">
        {!selection && <section className="surface detail-panel">
          <h2>岗位录入</h2>
          <form className="account-form" onSubmit={(event) => {
            event.preventDefault()
            const data = new FormData(event.currentTarget)
            const body = Object.fromEntries([...data].map(([key, value]) => [key, String(value).trim() || null]))
            void act(async () => { const created = await jobsApi.create(body); select(created.id); setDescription('') })
          }}>
            <div className="profile-fields">{Object.entries(fields).map(([name, label]) => <label key={name}>{label}
              <input name={name} required={name === 'position_name'} type={name === 'source_url' ? 'url' : 'text'} maxLength={name === 'source_url' ? 1000 : name === 'salary_range' ? 100 : 150} />
            </label>)}
            <label>岗位类型<select name="job_type"><option value="">未填写</option><option value="internship">实习</option><option value="full_time">全职</option><option value="other">其他</option></select></label></div>
            <label>导入 JD 文件<input type="file" accept=".txt,.pdf,.docx" disabled={busy} onChange={(event) => {
              const file = event.target.files?.[0]
              event.target.value = ''
              if (file) void act(async () => setDescription((await jobsApi.importText(file)).job_description), false)
            }} /></label>
            <label>JD 文本<textarea name="job_description" rows={7} required minLength={10} maxLength={12000} value={description} onChange={(event) => setDescription(event.target.value)} /></label>
            <button className="button button-filled" disabled={busy}>保存岗位</button>
          </form>
        </section>}
        {selection && !current && <p role="status">正在读取岗位…</p>}
        {current && <>
          <section className="surface detail-panel">
            <h2>{current.position_name}</h2>
            <p>{[current.company_name ?? current.parsed?.company_name, current.location ?? current.parsed?.location, current.parsed?.department].filter(Boolean).join(' · ')}</p>
            <p className="panel-description">{[current.job_type ? jobTypes[current.job_type] : current.parsed?.job_type, current.salary_range].filter(Boolean).join(' · ')}
              {current.source_url && <> <a className="text-brand underline" href={current.source_url} target="_blank" rel="noreferrer">查看岗位来源</a></>}
            </p>
            {current.parsed?.duties.length ? <><h3>工作职责</h3><ul>{current.parsed.duties.map((duty) => <li key={duty}>{duty}</li>)}</ul></> : null}
            {running && <p className="job-status" role="status">正在{running.kind === 'parse' ? '解析 JD' : '生成求职建议'}…</p>}
            {!running && latest?.state === 'failed' && <p className="form-error" role="alert">任务失败（{latest.error_code}）。可重新核对后重试。</p>}
            <div className="career-actions">
              <button className="button button-filled" disabled={paused} onClick={() => modelPreview(`/jobs/${current.id}/parse`)}>解析 JD</button>
              <button className="button button-outline" disabled={paused} onClick={() => setDeleteId(current.id)}>删除岗位</button>
            </div>
            {deleteId === current.id && <div className="career-delete">
              <p>会一并删除该岗位的匹配报告。</p><button className="button button-outline" disabled={paused} onClick={() => void act(async () => {
                await jobsApi.remove(current.id); setSelection(null); setDeleteId(null); setConfirmation(null)
              })}>确认删除岗位</button>{' '}<button className="button button-outline" onClick={() => setDeleteId(null)}>取消</button>
            </div>}
          </section>
          {confirmation && <section className="surface detail-panel">
            <h2>核对发送内容</h2>
            <p>接收服务 · {confirmation.host ?? '尚未配置'}</p>
            <pre className="max-h-56 overflow-auto whitespace-pre-wrap break-words">{typeof confirmation.payload.job_description === 'string' ? confirmation.payload.job_description : JSON.stringify(confirmation.payload, null, 2)}</pre>
            <button className="button button-filled" disabled={paused || !confirmation.host} onClick={() => void act(async () => {
              const result = await jobsApi.submitModel(confirmation.path, confirmation.host!, latest?.state === 'failed')
              setJob((previous) => previous?.id === current.id ? { ...previous, tasks: [result, ...previous.tasks.filter((task) => task.id !== result.id)] } : previous)
              setConfirmation(null)
            })}>同意发送并执行</button>{' '}<button className="button button-outline" onClick={() => setConfirmation(null)}>取消</button>
          </section>}
          {current.revision > 0 && <section className="surface detail-panel">
            <h2>核对岗位要求 {current.confirmed && <span className="badge">已确认</span>}</h2>
            <div className="grid gap-3">
              {requirements.map((item, index) => <div className="career-detail" key={index}>
                <div className="profile-fields">
                  <label>要求名称<input value={item.name} maxLength={150} onChange={(event) => setRequirements((previous) => previous.map((row, i) => i === index ? { ...row, name: event.target.value } : row))} /></label>
                  <label>重要性<select value={item.importance} onChange={(event) => setRequirements((previous) => previous.map((row, i) => i === index ? { ...row, importance: event.target.value } : row))}>
                    {Object.entries(importanceLabels).map(([key, label]) => <option key={key} value={key}>{label}</option>)}
                  </select></label>
                  <label>要求分类<select value={item.category} onChange={(event) => setRequirements((previous) => previous.map((row, i) => i === index ? { ...row, category: event.target.value } : row))}>
                    {Object.entries(categories).map(([key, label]) => <option key={key} value={key}>{label}</option>)}
                  </select></label>
                </div>
                <blockquote>{item.quote}</blockquote>
                <label>个人情况<select value={assessments[index] ?? ''} onChange={(event) => setAssessments((previous) => {
                  const result = { ...previous }
                  if (event.target.value) result[index] = event.target.value; else delete result[index]
                  return result
                })}><option value="">按现有证据判断</option><option value="not_provided">尚未提供信息</option><option value="no_evidence">暂时没有证据</option><option value="not_capable">明确不具备或不符合</option></select></label>
              </div>)}
              {!requirements.length && <p>未提取到可核对的要求。</p>}
              <button className="button button-outline" disabled={paused} onClick={() => void act(async () => {
                const saved = await jobsApi.confirm(current.id, current.revision, requirements)
                setJob({ ...saved, tasks: current.tasks })
                setRequirements(saved.requirements)
              })}>确认岗位要求</button>
              <label>简历内容版本<select value={content ?? ''} onChange={(event) => setContent(Number(event.target.value) || null)}>
                {!versions.length && <option value="">请先确认一份结构化简历</option>}
                {versions.map((item) => <option key={item.id} value={item.id}>{item.original_filename} · 第 {item.version} 版</option>)}
              </select></label>
              <button className="button button-filled" disabled={paused || !content || !current.confirmed || JSON.stringify(requirements) !== JSON.stringify(current.requirements)}
                onClick={() => content && void act(async () => {
                  const result = await jobsApi.match(current.id, { content_id: content, revision: current.revision, assessments })
                  setHistory((previous) => [result, ...previous.filter((item) => item.id !== result.id)])
                  setReportId(result.id)
                })}>计算匹配</button>
            </div>
          </section>}
          {report && <JobReport match={report} gaps={gapData?.id === report.id ? gapData.values : []} disabled={paused}
            onAdvice={() => modelPreview(`/job-matches/${report.id}/recommendations`)} />}
        </>}
      </div>
    </div>}
  </div>
}
