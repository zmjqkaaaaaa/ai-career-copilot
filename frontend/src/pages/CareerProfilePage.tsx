import { Feedback } from '../components/common/Feedback'
import { useEffect, useState } from 'react'
import { Link, useSearchParams } from 'react-router'
import { FileText, RotateCw, UploadCloud } from 'lucide-react'
import { EvidenceReport } from '../components/career/EvidenceReport'
import { OptimizationCard } from '../components/career/OptimizationCard'
import { ResumeFacts } from '../components/career/ResumeFacts'
import { useAuth } from '../hooks/AuthProvider'
import { errorMessage } from '../services/api'
import { careerApi, factGroups } from '../services/career'
import type { Analysis, Block, CareerReport, Content, Job, Optimization, Resume } from '../services/career'

const views = { resumes: '简历管理', profile: '职业画像', optimization: '优化建议' } as const
const parseLabels: Record<string, string> = { uploaded: '待解析', queued: '解析处理中', parsed: '已解析', failed: '解析失败', deleting: '待清理' }
const operationNames = { parse: '本地解析', extract: '结构化提取', analyze: '职业分析', optimize: '简历优化' } as const
const errors: Record<string, string> = {
  NO_RESUME_TEXT: '文件没有文字层，请上传可复制文字的 PDF 或 DOCX。',
  UNREADABLE_RESUME: '简历文件损坏或无法读取。',
  ENCRYPTED_PDF: '请先解除 PDF 密码保护。',
  PDF_TOO_LONG: 'PDF 超过 20 页。',
  PDF_TOO_COMPLEX: 'PDF 页面内容超过处理上限。',
  RESUME_TOO_LONG: '简历文字超过处理上限，请缩短后重新上传。',
  RESUME_FILE_MISSING: '找不到原始文件，请重新上传。',
  MODEL_AUTH_FAILED: '模型拒绝认证，请检查 API Key 与服务地址。',
  MODEL_RATE_LIMIT: '模型服务正在限流，请稍后手动重试。',
  MODEL_BALANCE_REQUIRED: '模型服务余额不足。',
  MODEL_CONNECTION_FAILED: '无法连接模型服务。',
  MODEL_TIMEOUT: '模型响应超时，可以手动重试。',
  MODEL_OUTPUT_INCOMPLETE: '模型返回为空或被截断，可以手动重试。',
  MODEL_OUTPUT_INVALID: '模型输出未通过结构校验，可以手动重试。',
  MODEL_EVIDENCE_INVALID: '模型未返回可以定位到原文的证据。',
  MODEL_CONFIG_CHANGED: '模型配置已更新，请重新提交任务。',
  MODEL_INPUT_TOO_LONG: '发送内容超出模型处理上限，请减少段落。',
  JOB_INTERRUPTED: '任务中断，请考虑手动重试。',
}
type Snapshot = { id: number; content: Content | null; preview: Block[]; jobs: Job[]; history: Analysis[]; optimization: Optimization[] }
const active = (job: Job) => job.state === 'queued' || job.state === 'running'

function elapsed(timestamp: string | null) {
  const time = timestamp ? Date.parse(timestamp.endsWith('Z') ? timestamp : timestamp + 'Z') : NaN
  return Number.isFinite(time) ? ` · ${Math.max(0, Math.floor((Date.now() - time) / 1000))} 秒` : ''
}

export function CareerProfilePage() {
  const [params, setParams] = useSearchParams()
  const linkedResume = Number(params.get('resume')) || null
  const linkedContent = linkedResume ? Number(params.get('content')) || null : null
  const { profile } = useAuth()
  const [view, setView] = useState<keyof typeof views>('resumes')
  const [resumes, setResumes] = useState<Resume[]>([])
  const [selected, setSelected] = useState<number | null>(linkedResume)
  const [snapshot, setSnapshot] = useState<Snapshot | null>(null)
  const [file, setFile] = useState<File | null>(null)
  const [fileInput, setFileInput] = useState(0)
  const [revision, setRevision] = useState(0)
  const [hidden, setHidden] = useState<number[]>([])
  const [reading, setReading] = useState(true)
  const [busy, setBusy] = useState(false)
  const [loadError, setLoadError] = useState('')
  const [actionError, setActionError] = useState('')
  const [progressError, setProgressError] = useState('')
  const [message, setMessage] = useState('')
  const [reportError, setReportError] = useState('')
  const [analysisId, setAnalysisId] = useState<number | null>(null)
  const [report, setReport] = useState<CareerReport | null>(null)
  const [target, setTarget] = useState<string | null>(null)
  const [confirmDelete, setConfirmDelete] = useState<number | null>(null)
  const [providerHost, setProviderHost] = useState<string | null>(null)
  const profileTarget = profile.state === 'ready' ? profile.data.target_position : null
  const targetDirection = target ?? (profileTarget || 'AI 产品经理')
  const selectedResume = resumes.find((item) => item.id === selected)
  const current = snapshot?.id === selected ? snapshot : null
  const currentContent = current?.content
  const activeJob = current?.jobs.find(active)
  const latest = current?.jobs[0]
  const disabled = busy || Boolean(activeJob)
  const reportId = current?.history.some((item) => item.id === analysisId) ? analysisId : current?.history[0]?.id

  useEffect(() => {
    const controller = new AbortController()
    careerApi.provider(controller.signal)
      .then(({ host }) => { if (!controller.signal.aborted) setProviderHost(host) })
      .catch((failure) => { if (!controller.signal.aborted) setLoadError(errorMessage(failure)) })
    return () => controller.abort()
  }, [revision])

  function reviewedSource() {
    return <details className="career-detail">
      <summary>查看将再次发送的已核对文本</summary>
      {currentContent?.model_blocks?.map((block) => <blockquote key={block.number}>{block.text}</blockquote>)}
    </details>
  }

  useEffect(() => {
    const controller = new AbortController()
    const { signal } = controller
    async function load() {
      setReading(true)
      setLoadError('')
      try {
        const list = await careerApi.list(signal)
        if (linkedResume && !list.some((item) => item.id === linkedResume)) list.unshift(await careerApi.read(linkedResume, signal))
        if (signal.aborted) return
        setResumes(list)
        const id = linkedResume ?? (list.some((item) => item.id === selected) ? selected : list[0]?.id ?? null)
        if (id !== selected) {
          setSelected(id)
          return
        }
        if (!id) { setSnapshot(null); return }
        const resume = list.find((item) => item.id === id)
        if (resume?.parse_status === 'deleting') {
          setSnapshot({ id, content: null, preview: [], jobs: [], history: [], optimization: [] })
          return
        }
        const [content, jobs, history, optimization] = await Promise.all([
          careerApi.content(id, signal, linkedContent), careerApi.jobs(id, signal), careerApi.analyses(id, signal), careerApi.optimizations(id, signal),
        ])
        if (linkedContent && !content) { setSnapshot(null); setLoadError('找不到该简历版本。'); return }
        const preview = content && !content.structured_data ? await careerApi.preview(id, content.id, signal) : []
        if (!signal.aborted) setSnapshot({ id, content, preview, jobs, history, optimization })
      } catch (failure) {
        if (!signal.aborted) setLoadError(errorMessage(failure))
      } finally {
        if (!signal.aborted) setReading(false)
      }
    }
    void load()
    return () => controller.abort()
  }, [selected, revision, linkedResume, linkedContent])

  useEffect(() => {
    if (!activeJob?.id) return
    const id = activeJob.id
    const controller = new AbortController()
    let timer: number
    async function poll() {
      try {
        const job = await careerApi.job(id, controller.signal)
        if (controller.signal.aborted) return
        setProgressError('')
        if (active(job)) {
          setSnapshot((prior) => prior && ({ ...prior, jobs: prior.jobs.map((entry) => entry.id === job.id ? job : entry) }))
          timer = window.setTimeout(() => void poll(), 1600)
        } else {
          setRevision((value) => value + 1)
        }
      } catch (failure) {
        if (!controller.signal.aborted) {
          setProgressError('暂时无法刷新任务状态，页面会自动重试。')
          timer = window.setTimeout(() => void poll(), 3500)
        }
      }
    }
    timer = window.setTimeout(() => void poll(), 1000)
    return () => { controller.abort(); window.clearTimeout(timer) }
  }, [activeJob?.id])

  useEffect(() => {
    if (view !== 'profile' || !reportId) return
    const controller = new AbortController()
    careerApi.profile(reportId, controller.signal)
      .then((data) => { if (!controller.signal.aborted) { setReport(data); setReportError('') } })
      .catch((failure) => { if (!controller.signal.aborted) setReportError(errorMessage(failure)) })
    return () => controller.abort()
  }, [reportId, view, revision])

  async function perform(action: () => Promise<unknown>, success = '') {
    setBusy(true)
    setActionError('')
    setProgressError('')
    setMessage('')
    try {
      await action()
      setMessage(success)
      setRevision((value) => value + 1)
    } catch (failure) { setActionError(errorMessage(failure)) }
    finally { setBusy(false) }
  }

  function select(id: number) {
    if (linkedResume) setParams({}, { replace: true })
    setSelected(id)
    setHidden([])
    setAnalysisId(null)
    setReportError('')
    setConfirmDelete(null)
    setActionError('')
    setMessage('')
  }

  const failed = (kind: Job['kind']) => current?.jobs.find((job) => job.kind === kind)?.state === 'failed'

  return <div className="career-page">
    <section className="hero" aria-labelledby="career-heading">
      <h1 id="career-heading">AI 职业画像</h1>
      <p>从简历定位能力证据，梳理目标方向并优化项目表达。</p>
    </section>
    {!linkedContent && <div className="career-tabs" role="group" aria-label="职业画像视图">
      {(Object.keys(views) as Array<keyof typeof views>).map((key) => <button type="button" key={key}
        className="button button-outline" aria-pressed={view === key} onClick={() => setView(key)}>{views[key]}</button>)}
    </div>}
    <div className="career-columns">
      <aside className="surface detail-panel career-files">
        <h2>我的简历</h2>
        <form className="account-form" onSubmit={(event) => {
          event.preventDefault()
          if (!file) return
          void perform(async () => {
            const uploaded = await careerApi.upload(file)
            select(uploaded.id)
            setFile(null)
            setFileInput((index) => index + 1)
            setView('resumes')
            try {
              await careerApi.parse(uploaded.id, false, false)
            } catch (failure) {
              setRevision((value) => value + 1)
              throw new Error(`文件已上传，本地解析未提交。请点击「本地解析」重试。 ${errorMessage(failure)}`)
            }
          }, '上传成功，已提交本地解析。')
        }}>
          <label>选择简历<input key={fileInput} type="file" accept=".pdf,.docx" onChange={(event) => {
            const candidate = event.target.files?.[0]
            setActionError('')
            if (candidate && (!/\.(pdf|docx)$/i.test(candidate.name) || candidate.size > 10 * 1024 * 1024)) {
              setActionError('请选择不超过 10 MB 的 PDF 或 DOCX。')
              setFile(null)
            } else setFile(candidate ?? null)
          }} /></label>
          <p className="panel-description">PDF 或 DOCX，最多 10 MB。PDF 需包含文字层。</p>
          <button className="button button-filled" disabled={busy || !file}><UploadCloud size={17} /> 上传简历</button>
        </form>
        {resumes.length === 0 && !reading && <p className="panel-description">还没有上传简历。</p>}
        {resumes.length > 0 && <ul className="career-files-list">{resumes.map((item) => <li key={item.id}>
          <button type="button" aria-pressed={selected === item.id} onClick={() => select(item.id)}>
            <FileText size={16} />
            <span>{item.original_filename}<small>{new Date(item.created_at.endsWith('Z') ? item.created_at : item.created_at + 'Z').toLocaleDateString('zh-CN')} · {parseLabels[item.parse_status] ?? item.parse_status}</small></span>
          </button>
        </li>)}</ul>}
      </aside>
      <div className="career-main">
        {loadError && <div className="surface detail-panel"><Feedback kind="error">{loadError}</Feedback>
          <button className="button button-outline" onClick={() => setRevision((index) => index + 1)}>重新读取</button></div>}
        {actionError && <Feedback kind="error">{actionError}</Feedback>}
        {activeJob && !linkedContent && progressError && <Feedback kind="error">{progressError}</Feedback>}
        {message && <Feedback kind="success">{message}</Feedback>}
        {reading && !current && <Feedback kind="loading">正在读取简历…</Feedback>}
        {activeJob && !linkedContent && <p className="job-status" role="status">
          {operationNames[activeJob.kind]} · {activeJob.state === 'queued'
            ? (activeJob.worker_available === false ? '后台处理服务未连接，任务仍在队列' : '排队中') + elapsed(activeJob.scheduled_at)
            : (activeJob.kind === 'parse' ? '正在本地读取文件' : '模型正在处理') + elapsed(activeJob.started_at)}
        </p>}
        {!activeJob && latest?.state === 'failed' && <Feedback kind="error">{operationNames[latest.kind]}失败。{errors[latest.error_code ?? ''] ?? '暂时无法完成，可手动重试。'}</Feedback>}
        {!selectedResume && !reading && <section className="surface detail-panel">
          <h2>从上传简历开始</h2><p className="panel-description">完成本地解析后，可以核对发给模型的内容。</p>
        </section>}
        {selectedResume && linkedContent && currentContent?.id === linkedContent && currentContent.structured_data && <section className="surface detail-panel">
          <div className="section-heading"><h2>{selectedResume.original_filename}</h2><span className="badge">第 {currentContent.version} 版 · 匹配来源</span></div>
          <details className="career-detail"><summary>查看本版核对过的简历原文</summary>
            {currentContent.model_blocks?.map((block) => <blockquote key={block.number} className="whitespace-pre-wrap">
              段落 {block.number} · {block.location}{'\n'}{block.text}
            </blockquote>)}
          </details>
          <ResumeFacts key={currentContent.id} facts={currentContent.structured_data} modelBlocks={currentContent.model_blocks ?? []}
            confirmed={currentContent.confirmed} disabled />
          <Link className="text-brand underline" to={`/career-profile?resume=${selectedResume.id}`} onClick={() => setView('resumes')}>打开这份简历的最新版本</Link>
        </section>}
        {selectedResume && !linkedContent && view === 'resumes' && <>
          <section className="surface detail-panel">
            <div className="section-heading"><h2>{selectedResume.original_filename}</h2><span className="badge">{parseLabels[selectedResume.parse_status]}</span></div>
            <div className="career-actions">
              {selectedResume.parse_status !== 'deleting' && <button className="button button-outline" disabled={disabled || reading} onClick={() => {
                setHidden([])
                void perform(() => careerApi.parse(selectedResume.id, Boolean(currentContent), failed('parse')))
              }}><RotateCw size={16} />{currentContent ? '重新解析' : '本地解析'}</button>}
              <button className="button button-outline" disabled={disabled || reading} onClick={() => setConfirmDelete(selectedResume.id)}>删除简历</button>
            </div>
            {confirmDelete === selectedResume.id && <div className="career-delete">
              <p>删除会同时移除这份简历的报告和优化记录。</p>
              <button className="button button-outline" disabled={disabled} onClick={() => void perform(async () => {
                await careerApi.delete(selectedResume.id)
                setConfirmDelete(null)
                setSelected(null)
              }, '已删除简历。')}>确认删除</button>{' '}
              <button className="button button-outline" onClick={() => setConfirmDelete(null)}>取消</button>
            </div>}
          </section>
          {currentContent && !currentContent.structured_data && <section className="surface detail-panel">
            <h2>核对简历原文</h2>
            <p className="panel-description">已尝试遮盖联系方式，请再检查姓名等个人信息。取消勾选可隐藏整段。选择本地整理时只在本地生成草稿。选择「同意发送并提取」时，所选文字会发送到 {providerHost ?? '尚未配置的模型服务'}。</p>
            <div className="career-source-list">
              {current?.preview.map((block) => <label key={block.number}>
                <input type="checkbox" checked={!hidden.includes(block.number)} onChange={(event) => setHidden((values) => event.target.checked ? values.filter((id) => id !== block.number) : [...values, block.number])} />
                <span><small>段落 {block.number} · {block.location}{block.section ? ' · ' + factGroups[block.section] : ''}</small><span>{block.text}</span></span>
              </label>)}
            </div>
            {current?.preview.some((block) => block.section && !hidden.includes(block.number)) &&
              <button className="button button-outline" disabled={disabled}
                onClick={() => void perform(() => careerApi.localDraft(selectedResume.id, currentContent.id, hidden), '已按原文章节整理本地草稿，请核对。')}>
                按原文章节整理（本地）
              </button>}
            <button className="button button-filled" disabled={disabled || !providerHost || !current?.preview.some((block) => !hidden.includes(block.number))}
              onClick={() => providerHost && void perform(() => careerApi.extract(selectedResume.id, currentContent.id, hidden, failed('extract'), providerHost))}>
              {failed('extract') ? '重试结构化提取' : '同意发送并提取'}
            </button>
          </section>}
          {currentContent?.structured_data && <section className="surface detail-panel">
            <div className="section-heading"><h2>结构化简历</h2><span className="badge">{currentContent.confirmed ? '已确认' : '待确认'} · 版本 {currentContent.version}</span></div>
            {currentContent.metadata_json?.method === 'local_sections' && <p className="panel-description">本地按原文标题整理。请核对分类和正文，未识别的标题下如有重要内容，可从原文补入。</p>}
            {Boolean(currentContent.metadata_json?.rejected) && <p className="panel-description">已排除 {currentContent.metadata_json?.rejected} 条无法核对原文的结果。</p>}
            <ResumeFacts key={currentContent.id} facts={currentContent.structured_data} modelBlocks={currentContent.model_blocks ?? []} confirmed={currentContent.confirmed} disabled={disabled}
              onSave={(facts) => void perform(() => careerApi.update(selectedResume.id, currentContent.id, facts), '已保存结构化简历。')} />
          </section>}
        </>}
        {selectedResume && !linkedContent && view === 'profile' && <>
          <section className="surface detail-panel">
            <h2>生成职业画像</h2>
            <form className="account-form" onSubmit={(event) => {
              event.preventDefault()
              if (providerHost && currentContent?.confirmed && targetDirection.trim()) {
                setAnalysisId(null)
                void perform(() => careerApi.analyze(selectedResume.id, currentContent.id, targetDirection.trim(), failed('analyze'), providerHost))
              }
            }}>
              <label>分析目标岗位<input value={targetDirection} maxLength={150} required onChange={(event) => setTarget(event.target.value)} /></label>
              {!currentContent?.confirmed && <p className="panel-description">请先在简历管理中确认结构化简历。</p>}
              {currentContent?.confirmed && <><p className="panel-description">生成时会将已核对的文本及分析方向发送到 {providerHost ?? '尚未配置的模型服务'}。</p>{reviewedSource()}</>}
              <button className="button button-filled" disabled={disabled || !providerHost || !currentContent?.confirmed || !targetDirection.trim()}>{failed('analyze') ? '重试职业分析' : '生成职业画像'}</button>
            </form>
          </section>
          {Boolean(current?.history.length) && <section className="surface detail-panel">
            <label className="career-history">分析历史
              <select value={reportId ?? ''} onChange={(event) => setAnalysisId(Number(event.target.value))}>
                {current?.history.map((entry) => <option key={entry.id} value={entry.id}>#{entry.id} · {entry.target_direction} · {entry.model_name}</option>)}
              </select>
            </label>
          </section>}
          {reportError && <Feedback kind="error">{reportError}</Feedback>}
          {report && report.analysis.id === reportId && <EvidenceReport result={report} />}
        </>}
        {selectedResume && !linkedContent && view === 'optimization' && <>
          <section className="surface detail-panel">
            <h2>简历优化</h2>
            <p className="panel-description">按「{targetDirection.trim() || 'AI 产品经理'}」方向生成建议。你可以在职业画像视图修改方向。</p>
            {!currentContent?.confirmed && <p className="panel-description">请先确认结构化简历。</p>}
            {currentContent?.confirmed && <><p className="panel-description">生成时会将已核对的文本及分析方向发送到 {providerHost ?? '尚未配置的模型服务'}。</p>{reviewedSource()}</>}
            <button className="button button-filled" disabled={disabled || !providerHost || !currentContent?.confirmed}
              onClick={() => currentContent && providerHost && void perform(() => careerApi.optimize(selectedResume.id, currentContent.id, targetDirection.trim() || 'AI 产品经理', failed('optimize'), providerHost))}>
              {failed('optimize') ? '重试生成建议' : '生成优化建议'}
            </button>
          </section>
          {current?.optimization.map((record) => <OptimizationCard key={record.id} record={record} disabled={disabled}
            onConfirm={(text) => void perform(() => careerApi.confirm(selectedResume.id, record.id, text), '已保存为独立文本版本。')} />)}
          {current?.jobs.some((job) => job.kind === 'optimize' && job.state === 'succeeded') && !current.optimization.length &&
            <p className="panel-description">模型未找到可核对原文的优化建议。</p>}
        </>}
      </div>
    </div>
  </div>
}
