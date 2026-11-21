import { useEffect, useState } from 'react'
import { Link, useLocation, useSearchParams } from 'react-router'
import { errorMessage } from '../services/api'
import { discoveryApi as api, downloadMarkdown } from '../services/discovery'
import type { Claim, Detail, JobInput, Prd, Preview, ProjectRecord, ResearchDetail, Session } from '../services/discovery'
import { CompetitorEditor, OpportunityEditor, PainEditor, SessionEditor } from '../components/discovery/DiscoveryEditors'

const areaNames = { dialogue:'探索对话', pain:'痛点工作台', market:'市场研究', opportunity:'机会评估' } as const
const directionLabels: Record<string, string> = { workflow:'流程工具', analysis:'数据分析', copilot:'辅助决策', knowledge:'知识检索', evaluation:'效果评估', research:'用户研究' }
const sourceLabels: Record<string, string> = { official:'官方材料', third_party:'第三方', user_review:'用户评价', unclassified:'待核对来源' }
const basisLabels: Record<string, string> = { evidence:'有证据', user_hypothesis:'用户假设', ai_inference:'AI 推断', unknown:'待验证' }
const competitorFields = { positioning:'定位', target_users:'目标用户', features:'核心功能', scenarios:'使用场景', experience:'使用体验', technology:'技术方案', business_model:'商业模式', advantages:'优势', limitations:'局限', differentiation:'差异化机会' } as const

function ResearchReport({ value, edit, disabled }: { value: ResearchDetail; edit:(research: number, id: number, body: ResearchDetail['competitors'][number]['data']) => void; disabled:boolean }) {
  const sources = value.data.sources
  function claim(item: Claim | null | undefined) {
    if (!item) return <span className="text-muted">待验证</span>
    return <>{item.text}{item.sources.map((id) => {
      const source = sources.find((entry) => entry.id === id)
      return source ? <a key={id} className="text-brand underline ml-1" href={source.url} rel="noreferrer" target="_blank">[{id}]</a> : null
    })}</>
  }
  return <div className="grid gap-4">
    <h3>{value.data.topic} · {value.created_at.slice(0, 10)}</h3>
    {value.data.status === 'insufficient_results' && <p role="status">未找到足以支持竞品结论的来源。可调整搜索词或补录资料。</p>}
    {value.data.findings.map((item, i) => <p key={i}>{claim(item)}</p>)}
    {value.competitors.length > 1 && <details className="career-detail"><summary>按维度比较竞品</summary>
      <div className="overflow-auto"><table className="w-full text-sm">
        <thead><tr><th scope="col" className="p-2 text-left">维度</th>
          {value.competitors.map(({ id, data }) => <th scope="col" className="p-2 text-left" key={id}>{data.product_name}</th>)}
        </tr></thead>
        <tbody>{Object.entries(competitorFields).map(([key, title]) => <tr className="border-t border-line" key={key}>
          <th scope="row" className="p-2 text-left">{title}</th>
          {value.competitors.map(({ id, data }) => <td className="p-2" key={id}>{claim(data[key as keyof typeof competitorFields])}</td>)}
        </tr>)}</tbody>
      </table></div>
    </details>}
    <div className="career-grid">{value.competitors.map(({ id, data }) => <article className="career-detail" key={id}>
      <h3>{data.product_name}</h3>
      {sources.filter((source) => source.id === data.official_source).map((source) => <a key={source.id} className="text-brand underline" href={source.url} rel="noreferrer" target="_blank">官网来源</a>)}
      <dl>{Object.entries(competitorFields).map(([key, title]) => <div key={key} className="mb-2"><dt className="font-semibold">{title}</dt><dd>{claim(data[key as keyof typeof competitorFields])}</dd></div>)}</dl>
      <details><summary>修正竞品</summary><CompetitorEditor key={data.product_name} value={data} disabled={disabled} onSave={(body) => edit(value.id, id, body)} /></details>
    </article>)}</div>
    <details className="career-detail"><summary>查看来源与采集时间（{sources.length}）</summary>
      <ol>{sources.map((source) => <li key={source.id}>
        <a className="text-brand underline" href={source.url} rel="noreferrer" target="_blank">{source.id}. {source.title || source.url}</a>
        <p>{sourceLabels[source.source_type]} · {source.method === 'tavily' ? 'Tavily 检索' : '用户补录'} · {source.collected_at.slice(0, 10)}</p>
        <blockquote>{source.excerpt}</blockquote>
      </li>)}</ol>
    </details>
  </div>
}

function ProjectCard({ item, disabled, update }: { item: ProjectRecord; disabled:boolean; update:(id:number, body: Parameters<typeof api.project>[1]) => void }) {
  const { data, id } = item
  const [direction, setDirection] = useState(data.direction)
  const [name, setName] = useState(data.name)
  const [positioning, setPositioning] = useState(data.positioning)
  return <article className="surface detail-panel">
    <h3>{data.name}</h3>
    <p>{directionLabels[data.direction]} · {data.difficulty} · {data.estimated_hours} 小时</p>
    {data.estimated_weeks != null && <p>按当前投入约 {data.estimated_weeks} 周{data.budget_fit === false && ' · 超出四周参考范围'}</p>}
    <dl className="career-points mt-3">{[
      ['项目背景',data.background],['目标用户',data.target_user],['用户痛点',data.pain],['产品定位',data.positioning],
      ['核心功能',data.features.join('、')],['AI 应用',data.ai_use],['技术栈',data.stack.join('、')],['预期学习',data.learning.join('、')],
      ['岗位关联',data.role_alignment],['差异化',data.differentiation],['主要风险',data.risks.join('、')],['推荐理由',data.reason],['展示成果',data.deliverable],
    ].map(([label,value]) => <div key={label}><dt className="font-semibold">{label}</dt><dd>{value}</dd></div>)}</dl>
    <div className="career-actions mt-3">
      <button disabled={disabled} className="button button-outline" onClick={() => update(id, { favorite: !item.favorite })}>{item.favorite ? '取消收藏' : '收藏项目'}</button>
      <button disabled={disabled || item.selected} className="button button-filled" onClick={() => update(id, { selected: true })}>{item.selected ? '已选定' : '选定项目'}</button>
    </div>
    <details className="career-detail mt-3"><summary>调整项目方向</summary>
      <form className="account-form" onSubmit={(event) => {
        event.preventDefault()
        const { budget_fit: _budget, estimated_weeks: _weeks, ...project } = data
        update(id, { project: { ...project, direction, name, positioning } })
      }}>
        <label>项目名称<input required maxLength={180} value={name} onChange={(e) => setName(e.target.value)} /></label>
        <label>项目方向<select value={direction} onChange={(e) => setDirection(e.target.value)}>{Object.entries(directionLabels).map(([key, value]) => <option key={key} value={key}>{value}</option>)}</select></label>
        <label>项目定位<textarea required maxLength={1200} value={positioning} onChange={(e) => setPositioning(e.target.value)} /></label>
        <button className="button button-outline" disabled={disabled}>保存项目调整</button>
      </form>
    </details>
  </article>
}

export function ProductDiscoveryPage() {
  const location = useLocation()
  const projectsPage = location.pathname === '/project-recommendations'
  const [parameters, setParameters] = useSearchParams()
  const selected = Number(parameters.get('session')) || null
  const [sessions, setSessions] = useState<Session[]>([])
  const [record, setRecord] = useState<Detail | null>(null)
  const [tick, refresh] = useState(0)
  const [area, setArea] = useState<keyof typeof areaNames>('dialogue')
  const [title, setTitle] = useState('')
  const [message, setMessage] = useState('')
  const [painId, setPainId] = useState<number | null>(null)
  const [researchId, setResearchId] = useState<number | null>(null)
  const [opportunityId, setOpportunityId] = useState<number | null>(null)
  const [query, setQuery] = useState('')
  const [url, setUrl] = useState('')
  const [sourceTitle, setSourceTitle] = useState('')
  const [excerpt, setExcerpt] = useState('')
  const [sourceType, setSourceType] = useState('official')
  const [sources, setSources] = useState<NonNullable<JobInput['sources']>>([])
  const [research, setResearch] = useState<ResearchDetail | null>(null)
  const [batchId, setBatchId] = useState<number | null>(null)
  const [compare, setCompare] = useState(false)
  const [prdList, setPrdList] = useState<Omit<Prd, 'content'>[]>([])
  const [prdId, setPrdId] = useState<number | null>(null)
  const [prd, setPrd] = useState<Prd | null>(null)
  const [approval, setApproval] = useState<(Preview & { body: JobInput; session: number }) | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [messageLimit, setMessageLimit] = useState(20)
  const current = record?.id === selected ? record : null
  const pending = current?.tasks.find((task) => ['queued','running'].includes(task.state))
  const latest = current?.tasks[0]
  const disabled = busy || Boolean(pending)
  const pain = current?.pain_points.find((item) => item.id === painId) ?? current?.pain_points[0]
  const relevantResearch = current?.research.filter((item) => item.pain_point_id === pain?.id) ?? []
  const pickedResearch = relevantResearch.find((item) => item.id === researchId) ?? relevantResearch[0]
  const opportunity = current?.opportunities.find((item) => item.id === opportunityId) ?? current?.opportunities[0]
  const activeProject = current?.projects.find((item) => item.selected)
  const activeProjectId = activeProject?.id
  const batches = [...new Set(current?.projects.map((item) => item.batch_id))]
  const shownBatch = batches.includes(batchId ?? -1) ? batchId : batches[0]
  const projects = current?.projects.filter((item) => item.batch_id === shownBatch) ?? []

  useEffect(() => {
    let ignore = false
    api.list().then((items) => { if (!ignore) setSessions(items) }).catch((e) => { if (!ignore) setError(errorMessage(e)) })
    return () => { ignore = true }
  }, [tick])
  useEffect(() => {
    if (!selected) return
    let ignore = false
    api.get(selected).then((item) => { if (!ignore) setRecord(item) }).catch((e) => { if (!ignore) setError(errorMessage(e)) })
    return () => { ignore = true }
  }, [selected, tick])
  useEffect(() => {
    if (!pending) return
    const timer = window.setTimeout(() => refresh((n) => n + 1), 1500)
    return () => window.clearTimeout(timer)
  }, [pending, tick])
  useEffect(() => {
    if (!pickedResearch || area !== 'market') return
    let ignore = false
    api.research(pickedResearch.id).then((value) => { if (!ignore) setResearch(value) }).catch((e) => { if (!ignore) setError(errorMessage(e)) })
    return () => { ignore = true }
  }, [pickedResearch?.id, area, tick])
  useEffect(() => {
    if (!activeProjectId || !projectsPage) return
    let ignore = false
    api.prds(activeProjectId).then(async (versions) => {
      if (ignore) return
      setPrdList(versions)
      const version = versions.find((item) => item.id === prdId) ?? versions[0]
      const saved = version ? await api.prd(version.id) : null
      if (!ignore) setPrd(saved)
    }).catch((e) => { if (!ignore) setError(errorMessage(e)) })
    return () => { ignore = true }
  }, [activeProjectId, projectsPage, prdId, tick])

  function select(id: number | null) {
    setParameters(id ? {session: String(id)} : {})
    setApproval(null); setPainId(null); setResearchId(null); setOpportunityId(null); setBatchId(null)
    setResearch(null); setPrd(null); setPrdList([]); setPrdId(null); setMessageLimit(20)
    setMessage(''); setQuery(''); setSources([]); setUrl(''); setSourceTitle(''); setExcerpt('')
    setCompare(false)
  }

  async function act(action: () => Promise<void>, reload = true) {
    setBusy(true); setError('')
    try { await action(); if (reload) refresh((n) => n + 1) }
    catch (e) { setError(errorMessage(e)) }
    finally { setBusy(false) }
  }

  function preview(body: JobInput) {
    if (!current) return
    const session = current.id
    void act(async () => setApproval({ ...await api.preview(session, body), body, session }), false)
  }

  const visibleApproval = approval?.session === current?.id ? approval : null
  const versionLink = current ? `?session=${current.id}` : ''
  return <div className="career-page">
    <section className="hero"><h1>{projectsPage ? '项目推荐与 PRD' : '兴趣探索'}</h1><p>{projectsPage ? '比较项目方向，把选定方案整理成可验证的需求草稿。' : '从一次具体经历出发，找出值得验证的问题。'}</p></section>
    <div className="career-columns">
      <aside className="surface detail-panel">
        <h2>探索会话</h2>
        <form className="account-form" onSubmit={(e) => { e.preventDefault(); void act(async () => { const item = await api.create(title.trim()); select(item.id); setTitle('') }) }}>
          <label>新会话名称<input value={title} maxLength={150} required onChange={(e) => setTitle(e.target.value)} /></label>
          <button className="button button-filled" disabled={busy || !title.trim()}>创建探索会话</button>
        </form>
        <ul className="career-files-list">{sessions.map((item) => <li key={item.id}>
          <button aria-pressed={selected === item.id} onClick={() => select(item.id)}>{item.title}</button>
        </li>)}</ul>
      </aside>
      <div className="career-main">
        {error && <p className="form-error" role="alert">{error}</p>}
        {!current && <section className="surface detail-panel"><h2>{selected ? '正在读取会话…' : '创建或选择一个探索会话'}</h2></section>}
        {current && <>
          <div className="career-tabs"><Link className="button button-outline" to={(projectsPage ? '/interest-exploration' : '/project-recommendations') + versionLink}>
            {projectsPage ? '返回兴趣探索' : '进入项目推荐'}
          </Link>{!projectsPage && (Object.keys(areaNames) as (keyof typeof areaNames)[]).map((key) =>
            <button key={key} className="button button-outline" aria-pressed={area === key} onClick={() => setArea(key)}>{areaNames[key]}</button>)}</div>
          {pending && <p className="job-status" role="status">{pending.state === 'queued' ? '任务已排队' : '任务处理中'}</p>}
          {!pending && latest?.state === 'failed' && <div className="form-error" role="alert">
            <p>任务失败（{latest.error_code}）</p><button className="button button-outline" disabled={busy || latest.attempt >= 3}
              onClick={() => void act(async () => { await api.retry(latest.id) })}>重试该任务</button>
          </div>}
          {visibleApproval && <section className="surface detail-panel">
            <h2>核对发送内容</h2><p>模型服务 · {visibleApproval.model_host ?? '尚未配置'}</p>
            {visibleApproval.search_host && <p>搜索服务 · {visibleApproval.search_host}。搜索请求使用下列查询词。</p>}
            <pre className="max-h-64 overflow-auto whitespace-pre-wrap wrap-anywhere">{JSON.stringify(visibleApproval.payload, null, 2)}</pre>
            <button className="button button-filled" disabled={disabled || !visibleApproval.model_host} onClick={() => void act(async () => {
              await api.send(current.id, visibleApproval.body, visibleApproval.approval)
              if (visibleApproval.body.kind === 'turn') setMessage('')
              if (visibleApproval.body.kind === 'recommend') setBatchId(null)
              if (visibleApproval.body.kind === 'prd') setPrdId(null)
              setApproval(null)
            })}>同意发送并执行</button>{' '}
            <button className="button button-outline" onClick={() => setApproval(null)}>取消</button>
          </section>}
          {!projectsPage && area === 'dialogue' && <>
            <section className="surface detail-panel"><h2>探索偏好</h2>
              <SessionEditor key={`${current.id}-${current.mode}-${current.direction}-${current.weekly_hours}`} session={current} disabled={disabled}
                onSave={(value) => void act(async () => { await api.session(value) })} />
              <details className="career-detail mt-3"><summary>已有背景摘要</summary>
                <p>专业 · {[current.background.undergraduate_major, current.background.graduate_major].filter(Boolean).join('、') || '待补充'}</p>
                <p>目标岗位 · {String(current.background.target_position ?? '待补充')}</p>
                <p>技能 · {Array.isArray(current.background.skills) ? current.background.skills.join('、') : '待补充'}</p>
                <details><summary>展开经历、能力与岗位差距</summary><pre className="whitespace-pre-wrap wrap-anywhere">{JSON.stringify(current.background, null, 2)}</pre></details>
              </details>
              <div className="career-actions mt-3">{current.interests.map(({ id, data }) => <details className="career-detail" key={id}>
                <summary>{data.name} · {data.origin === 'stated' ? '用户明确表达' : 'AI 推断'}</summary><p>{data.category} · {data.reason}</p>
                <form className="account-form" onSubmit={(event) => {
                  event.preventDefault()
                  const name = String(new FormData(event.currentTarget).get('interest') ?? '').trim()
                  if (name) void act(async () => { await api.interest(current.id, id, { name, category: data.category, origin:'stated', reason:'用户手动修正或确认', confidence:'high' }) })
                }}><label>兴趣名称<input name="interest" required maxLength={180} defaultValue={data.name}/></label>
                  <button className="button button-outline" disabled={disabled}>确认兴趣</button></form>
              </details>)}</div>
            </section>
            <section className="surface detail-panel"><h2>探索对话</h2>
              {!current.messages.length && <p>说说你最近遇到的一件具体问题，当时你是怎么处理的？</p>}
              {current.messages.length > messageLimit && <button className="button button-outline" onClick={() => setMessageLimit((n) => n + 20)}>显示更多历史</button>}
              {current.messages.slice(-messageLimit).map((item) => <article className="career-detail mb-2" key={item.id}>
                <strong>{item.role === 'user' ? '我' : '探索导师'}</strong><p className="whitespace-pre-wrap">{item.content}</p>
                {item.details && <><ul>{item.details.questions.map((question) => <li key={question}>{question}</li>)}</ul><p className="text-muted">{item.details.learning_note}</p></>}
              </article>)}
              <form className="account-form" onSubmit={(e) => { e.preventDefault(); preview({ kind:'turn', message:message.trim() }) }}>
                <label>我的回答<textarea required maxLength={1200} value={message} onChange={(e) => setMessage(e.target.value)} /></label>
                <button className="button button-filled" disabled={disabled || !message.trim()}>预览并发送本轮</button>
              </form>
            </section>
          </>}
          {!projectsPage && area !== 'dialogue' && <section className="surface detail-panel account-form">
            <label>当前痛点<select value={pain?.id ?? ''} onChange={(e) => { setPainId(Number(e.target.value)); setResearchId(null) }}>
              {!current.pain_points.length && <option value="">请先从对话提取痛点</option>}
              {current.pain_points.map((item) => <option key={item.id} value={item.id}>{item.data.pain_point_name}</option>)}
            </select></label>
            {area === 'pain' && <button className="button button-filled" disabled={disabled || !current.messages.length}
              onClick={() => preview({ kind:'pain' })}>从对话提取痛点</button>}
          </section>}
          {!projectsPage && area === 'pain' && pain && <section className="surface detail-panel"><h2>痛点证据与访谈</h2>
            <PainEditor key={`${pain.id}-${pain.revision}`} item={pain} disabled={disabled} onSave={(value) => void act(async () => { await api.pain(value) })} />
          </section>}
          {!projectsPage && area === 'market' && pain && <>
            <section className="surface detail-panel account-form"><h2>市场研究</h2>
              {!current.search_configured && <p className="panel-description">本地尚未配置 Tavily。可先补录公开资料并分析。</p>}
              <label>Tavily 搜索词，每行一条，最多三条<textarea value={query} onChange={(e) => setQuery(e.target.value)} rows={3} /></label>
              <button className="button button-filled" disabled={disabled || !current.search_configured || !query.trim()} onClick={() => preview({
                kind:'research', reference_id: pain.id, queries:query.split('\n').map((part) => part.trim()).filter(Boolean).slice(0,3), sources,
              })}>预览联网搜索</button>
              <details className="career-detail"><summary>补录公开资料（{sources.length}）</summary>
                <form className="account-form" onSubmit={(e) => {
                  e.preventDefault()
                  setSources((values) => [...values, { url, title: sourceTitle, excerpt, source_type: sourceType }])
                  setUrl(''); setSourceTitle(''); setExcerpt('')
                }}>
                  <label>来源网址<input required type="url" value={url} onChange={(e) => setUrl(e.target.value)} /></label>
                  <label>来源标题<input required maxLength={180} value={sourceTitle} onChange={(e) => setSourceTitle(e.target.value)} /></label>
                  <label>相关原文<textarea required maxLength={1200} value={excerpt} onChange={(e) => setExcerpt(e.target.value)} /></label>
                  <label>资料类型<select value={sourceType} onChange={(e) => setSourceType(e.target.value)}>{Object.entries(sourceLabels).map(([key,value]) => <option key={key} value={key}>{value}</option>)}</select></label>
                  <button className="button button-outline" disabled={disabled || sources.length >= 10}>添加资料</button>
                </form>
                {sources.map((source, index) => <p key={index}>{source.title} <button className="text-brand underline" onClick={() => setSources((items) => items.filter((_, i) => i !== index))}>移除</button></p>)}
                <button className="button button-filled mt-2" disabled={disabled || !sources.length} onClick={() => preview({ kind:'research', reference_id:pain.id, sources })}>预览并分析补录资料</button>
              </details>
              {relevantResearch.length > 0 && <label>研究历史<select value={pickedResearch?.id} onChange={(e) => setResearchId(Number(e.target.value))}>{relevantResearch.map((item) => <option key={item.id} value={item.id}>#{item.id} · {item.created_at.slice(0, 10)}</option>)}</select></label>}
            </section>
            {research?.id === pickedResearch?.id && research && <section className="surface detail-panel"><ResearchReport value={research} disabled={disabled}
              edit={(run, id, data) => void act(async () => { await api.competitor(run, id, data) })} /></section>}
          </>}
          {!projectsPage && area === 'opportunity' && <section className="surface detail-panel account-form">
            <h2>产品机会分析</h2>
            <button className="button button-filled" disabled={disabled || !pain} onClick={() => pain && preview({ kind:'opportunity', reference_id:pain.id, research_id:pickedResearch?.id })}>预览机会评估</button>
            {current.opportunities.length > 0 && <label>评估历史<select value={opportunity?.id} onChange={(e) => setOpportunityId(Number(e.target.value))}>{current.opportunities.map((item) => <option value={item.id} key={item.id}>评估 #{item.id} · 痛点 #{item.pain_point_id}</option>)}</select></label>}
            {opportunity && <><p>机会分 · {opportunity.data.score ?? '证据不足'} · 证据覆盖率 {opportunity.data.coverage}%</p>
              <p>用户问题 · {pain?.data.user_problem ?? '请核对评估关联的痛点'}</p>
              <p>市场空间 · {opportunity.research_id ? '查阅本次研究中的竞品与证据' : '待补充市场研究'}</p>
              <p>差异化 · {opportunity.data.differentiation}</p><p>风险 · {opportunity.data.risks.join('、') || '待验证'}</p>
              <p>技术可行性 · {opportunity.data.feasibility}</p><p>验证计划 · {opportunity.data.validation_plan}</p>
              <div className="career-grid">{opportunity.data.ratings.map((item) => <div className="career-detail" key={item.dimension}>
                <strong>{item.label}</strong><p>{item.rating ?? '待验证'} / 4 · {basisLabels[item.basis]}</p><p>{item.reason}</p>
                {item.references.length > 0 && <details><summary>评分引用</summary><pre className="whitespace-pre-wrap wrap-anywhere">{JSON.stringify(item.references.map((key) => opportunity.data.evidence[key]), null, 2)}</pre></details>}
              </div>)}</div>
              <OpportunityEditor key={opportunity.id} item={opportunity} disabled={disabled} onSave={(body) => void act(async () => { await api.opportunity(opportunity, body); setOpportunityId(null) })} />
            </>}
          </section>}
          {projectsPage && <>
            <section className="surface detail-panel account-form"><h2>个性化项目推荐</h2>
              <label>采用的机会评估<select value={opportunity?.id ?? ''} onChange={(e) => setOpportunityId(Number(e.target.value))}>
                {!current.opportunities.length && <option value="">请先完成机会评估</option>}
                {current.opportunities.map((item) => <option key={item.id} value={item.id}>评估 #{item.id} · {item.data.score ?? '待评分'}</option>)}
              </select></label>
              <button className="button button-filled" disabled={disabled || !opportunity} onClick={() => opportunity && preview({
                kind:'recommend', reference_id:opportunity.id, regenerate:current.projects.some((item) => item.opportunity_id === opportunity.id),
              })}>{projects.length ? '重新推荐项目' : '预览项目推荐'}</button>
              {!!batches.length && <label>推荐历史<select value={shownBatch ?? ''} onChange={(e) => setBatchId(Number(e.target.value))}>{batches.map((id) => <option key={id} value={id}>推荐批次 #{id}</option>)}</select></label>}
              {!!projects.length && <button className="button button-outline" aria-pressed={compare} onClick={() => setCompare((old) => !old)}>比较当前方案</button>}
              {compare && <div className="overflow-auto"><table className="w-full text-sm"><thead><tr>{['项目','方向','工时','难度','展示成果'].map((label) => <th key={label} className="p-2 text-left">{label}</th>)}</tr></thead><tbody>
                {projects.map(({ id,data }) => <tr className="border-t border-line" key={id}>{[data.name,directionLabels[data.direction],data.estimated_hours,data.difficulty,data.deliverable].map((item,index) => <td key={index} className="p-2">{item}</td>)}</tr>)}
              </tbody></table></div>}
            </section>
            <div className="career-grid">{projects.map((item) => <ProjectCard key={`${item.id}-${item.data.name}-${item.data.direction}`} item={item} disabled={disabled}
              update={(id, body) => void act(async () => { await api.project(id, body); if (body.selected) { setPrdId(null); setPrdList([]); setPrd(null) } })} />)}</div>
            {activeProject && <section className="surface detail-panel account-form"><h2>PRD 工作台</h2><p>选定项目 · {activeProject.data.name}</p>
              <Link className="button button-outline" to={`/project-workspace?recommendation=${activeProject.id}`}>在项目工作台关联仓库</Link>
              <button className="button button-filled" disabled={disabled} onClick={() => preview({ kind:'prd', reference_id:activeProject.id, regenerate:prdList.length > 0 })}>{prdList.length ? '重新生成 PRD' : '预览 PRD 生成'}</button>
              {!!prdList.length && <label>PRD 历史版本<select value={prd?.id ?? ''} onChange={(e) => setPrdId(Number(e.target.value))}>{prdList.map((item) => <option key={item.id} value={item.id}>第 {item.version} 版 · {item.origin === 'ai_draft' ? 'AI 草稿' : '用户编辑'}</option>)}</select></label>}
              {prd && <form className="account-form" onSubmit={(e) => { e.preventDefault(); void act(async () => { const saved = await api.save(prd); setPrd(saved); setPrdId(saved.id) }) }}>
                <label>PRD 标题<input maxLength={180} required value={prd.title} onChange={(e) => setPrd({ ...prd, title:e.target.value })} /></label>
                <label>PRD 正文<textarea rows={16} required maxLength={18000} value={prd.content} onChange={(e) => setPrd({ ...prd, content:e.target.value })} /></label>
                <div className="career-actions"><button className="button button-filled" disabled={disabled || prd.id !== prdList[0]?.id}>保存新版本</button>
                  <button type="button" className="button button-outline" onClick={() => downloadMarkdown(prd)}>导出 Markdown</button></div>
              </form>}
            </section>}
          </>}
        </>}
      </div>
    </div>
  </div>
}
