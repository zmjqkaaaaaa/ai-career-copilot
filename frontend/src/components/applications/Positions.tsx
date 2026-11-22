import { useEffect, useState, type FormEvent } from 'react'
import { Link } from 'react-router'
import { ApiError } from '../../services/api'
import { applications, field, type Position, type ResumeVersion } from '../../services/applications'
import { jobsApi, type Gap, type Match } from '../../services/jobs'
import { JobReport } from '../jobs/JobReport'
import { Panel, showFailure, type Run } from './shared'

const filters = [
  ['q','搜索岗位'], ['company','筛选公司'], ['title','筛选岗位名称'], ['city','筛选城市'],
  ['industry','筛选行业'], ['education','筛选学历'], ['skill','筛选技能'],
  ['published_from','发布起始日'], ['published_to','发布截止日'],
]
const fields = [
  ['position_name','岗位名称'], ['company_name','公司名称'], ['location','城市'],
  ['salary_range','薪资范围'], ['source_url','招聘原链接'],
]
const details = [
  ['industry','行业'], ['education','学历要求'], ['major','专业要求'],
  ['experience','经验要求'], ['source','招聘来源'], ['published_at','发布日期'],
] as const
const sourceStates = { unknown: '未知', open: '招聘中', closed: '已结束', unavailable: '链接失效' }

function PositionForm({ position, run, saved, cancel, busy }: {
  position: Position | null; run: Run; saved: (id: number) => void; cancel: () => void; busy: boolean
}) {
  const meta = position?.discovery_metadata
  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const data = new FormData(event.currentTarget)
    const job = { ...Object.fromEntries(fields.map(([key]) => [key, field(data, key)])),
      job_description: field(data, 'job_description') ?? '', job_type: field(data, 'job_type') }
    const metadata = { ...Object.fromEntries(details.map(([key]) => [key, field(data, key)])),
      skills: (field(data, 'skills') ?? '').split(/[,，、]/).map((item) => item.trim()).filter(Boolean),
      duties: field(data, 'duties'), requirements_text: field(data, 'requirements_text'),
      source_status: field(data, 'source_status') }
    void run(async () => {
      const stored = position ? await applications.updatePosition(position.id, { job, metadata })
        : await applications.capture({ ...job, metadata })
      saved(stored.id)
    })
  }
  return <form className="account-form" onSubmit={submit}>
    <div className="career-grid">
      {fields.map(([key, label]) => <label key={key}>{label}<input name={key} defaultValue={position?.[key as keyof Position] as string ?? ''}
        required={key === 'position_name'} type={key === 'source_url' ? 'url' : 'text'} /></label>)}
      <label>岗位类别<select name="job_type" defaultValue={position?.job_type ?? ''}>
        <option value="">未知</option><option value="internship">实习</option><option value="full_time">全职</option><option value="other">其他</option>
      </select></label>
      {details.map(([key, label]) => <label key={key}>{label}<input name={key} defaultValue={meta?.[key] ?? ''}
        type={key === 'published_at' ? 'date' : 'text'} /></label>)}
      <label>技能要求<input name="skills" placeholder="用逗号分隔" defaultValue={meta?.skills?.join('，')} /></label>
      <label>招聘状态<select name="source_status" defaultValue={meta?.source_status ?? 'unknown'}>
        {Object.entries(sourceStates).map(([key, label]) => <option key={key} value={key}>{label}</option>)}
      </select></label>
    </div>
    <label>招聘 JD<textarea name="job_description" maxLength={12000} rows={5}
      defaultValue={position?.job_description} /></label>
    <p>可先保存原链接，补齐 JD 后再分析。</p>
    <label>岗位职责摘要<textarea name="duties" maxLength={1000} defaultValue={meta?.duties ?? ''} /></label>
    <label>招聘要求摘要<textarea name="requirements_text" maxLength={1000} defaultValue={meta?.requirements_text ?? ''} /></label>
    <div className="flex flex-wrap gap-2">
      <button className="button button-filled" disabled={busy}>保存岗位</button>
      <button className="button button-outline" type="button" onClick={cancel}>取消</button>
    </div>
  </form>
}

export function Positions({ favorites, selected, select, versions, refresh, run, error, applied, busy }: {
  favorites: boolean; selected: number | null; select: (id?: number) => void;
  versions: ResumeVersion[]; refresh: number; run: Run; error: (message: string) => void;
  applied: () => void; busy: boolean
}) {
  const [positions, setPositions] = useState<Position[]>([])
  const [position, setPosition] = useState<Position | null>(null)
  const [query, setQuery] = useState('')
  const [offset, setOffset] = useState(0)
  const [editing, setEditing] = useState<'new' | 'edit' | null>(null)
  const [confirmArchive, setConfirmArchive] = useState(false)
  const [match, setMatch] = useState<Match | null>(null)
  const [gaps, setGaps] = useState<Gap[]>([])
  const [loaded, setLoaded] = useState(false)
  const active = position?.id === selected ? position : null

  useEffect(() => {
    let ignore = false
    const search = new URLSearchParams(query)
    search.set('offset', String(offset))
    if (favorites) search.set('favorite', 'true')
    applications.positions(search.toString()).then((rows) => {
      if (!ignore) { setPositions(rows); setLoaded(true) }
    }).catch((failure) => { if (!ignore) showFailure(failure, error) })
    return () => { ignore = true }
  }, [query, favorites, offset, refresh, error])

  useEffect(() => {
    if (!selected) return
    let ignore = false
    void Promise.all([applications.position(selected),
      applications.match(selected).catch((failure) => {
        if (failure instanceof ApiError && failure.status === 404) return null
        throw failure
      })]).then(([row, report]) => {
      if (!ignore) { setPosition(row); setMatch(report?.revision === row.revision ? report : null) }
    }).catch((failure) => { if (!ignore) showFailure(failure, error) })
    return () => { ignore = true }
  }, [selected, refresh, error])

  useEffect(() => {
    if (!match) return
    let ignore = false
    jobsApi.gaps(match.id).then((result) => { if (!ignore) setGaps(result) })
      .catch((failure) => { if (!ignore) showFailure(failure, error) })
    return () => { ignore = true }
  }, [match, error])

  return <>
    <Panel title={favorites ? '岗位收藏' : '岗位发现'}>
      <p>搜索你已保存的岗位。可粘贴招聘 JD 或记录原始链接。</p>
      <form className="account-form" onSubmit={(event) => {
        event.preventDefault()
        setOffset(0)
        const data = new FormData(event.currentTarget)
        setQuery(new URLSearchParams(filters.flatMap(([key]) => {
          const value = field(data, key)
          return value ? [[key, value]] : []
        })).toString())
      }}>
        <div className="application-fields">
          {filters.map(([key,label]) => <label key={key}>{label}<input name={key} type={key.startsWith('published_') ? 'date' : 'text'} /></label>)}
        </div>
        <div className="flex flex-wrap gap-2">
          <button className="button button-outline">筛选</button>
          <button className="button button-outline" type="reset" onClick={() => { setQuery(''); setOffset(0) }}>重置筛选</button>
          {!favorites && <button className="button button-filled" type="button" onClick={() => setEditing('new')}>录入岗位</button>}
        </div>
      </form>
      <ul className="application-list">
        {positions.map((item) => <li key={item.id}>
          <button type="button" className="application-link" aria-pressed={selected === item.id} onClick={() => {
            select(item.id); setEditing(null); setConfirmArchive(false)
          }}>{item.position_name} · {item.company_name ?? '公司未知'}</button>
          <span>{item.location ?? '城市未知'}{item.latest_score != null && ` · 匹配 ${item.latest_score}`}</span>
        </li>)}
        {loaded && positions.length === 0 && <li>暂无符合条件的岗位。</li>}
      </ul>
      <div className="flex gap-2">
        {offset > 0 && <button className="button button-outline" onClick={() => setOffset(offset - 50)}>上一页</button>}
        {positions.length === 50 && <button className="button button-outline" onClick={() => setOffset(offset + 50)}>下一页</button>}
      </div>
    </Panel>
    {editing && <Panel title={editing === 'edit' ? '编辑已录入岗位' : '录入招聘岗位'}>
      <PositionForm key={editing === 'edit' ? selected : 'new'} position={editing === 'edit' ? active : null} run={run}
        busy={busy} saved={(id) => { select(id); setEditing(null) }} cancel={() => setEditing(null)} />
    </Panel>}
    {active && <Panel title={active.position_name}>
      <p>{active.company_name ?? '公司未知'} · {active.location ?? '城市未知'} · 薪资 {active.salary_range || '未知'}</p>
      <p>来源 {active.discovery_metadata?.source ?? '未知'} · 招聘状态 {sourceStates[active.discovery_metadata?.source_status as keyof typeof sourceStates] ?? '未知'}
        {' · 发布日期 '}{active.discovery_metadata?.published_at ?? '未知'}</p>
      <p>录入日期 {active.created_at.slice(0, 10)}</p>
      {details.slice(0, 4).map(([key, label]) => <p key={key}>{label} {active.discovery_metadata?.[key] ?? '未知'}</p>)}
      <p>技能 {active.discovery_metadata?.skills?.join('、') || '未知'}</p>
      {active.discovery_metadata?.duties && <p>岗位职责 {active.discovery_metadata.duties}</p>}
      {active.discovery_metadata?.requirements_text && <p>招聘要求 {active.discovery_metadata.requirements_text}</p>}
      {active.source_url && <a className="application-link" href={active.source_url} target="_blank" rel="noreferrer">打开招聘原链接</a>}
      <details><summary>查看原始 JD</summary><p className="whitespace-pre-wrap">{active.job_description || '待补充'}</p></details>
      <div className="flex flex-wrap gap-2">
        <button className="button button-outline" disabled={busy} onClick={() => void run(async () => {
          setPosition(await applications.updatePosition(active.id, { favorite: !active.favorite }))
        })}>{active.favorite ? '取消收藏' : '收藏岗位'}</button>
        <button className="button button-outline" onClick={() => setEditing('edit')}>编辑岗位</button>
        <Link className="button button-outline" to={`/job-matching?job=${active.id}`}>前往岗位匹配</Link>
        <Link className="button button-outline" to={`?tab=versions&job=${active.id}`}>定制此岗位简历</Link>
        {!active.archived && <button className="button button-outline" onClick={() => setConfirmArchive(true)}>移除岗位</button>}
      </div>
      {confirmArchive && <div className="flex flex-wrap items-center gap-2">
        <p>有关联投递的岗位会归档，其他岗位将移除。</p>
        <button className="button button-outline" disabled={busy} onClick={() => void run(async () => {
          await applications.archive(active.id); select(); setEditing(null); setConfirmArchive(false)
        })}>确认移除</button>
        <button className="button button-outline" onClick={() => setConfirmArchive(false)}>取消移除</button>
      </div>}
      {match && <JobReport match={match} gaps={gaps} />}
      {!active.archived && <form className="account-form" onSubmit={(event) => {
        event.preventDefault()
        const data = new FormData(event.currentTarget)
        void run(async () => {
          const version = versions.find((item) => item.id === Number(field(data, 'version')))
          await applications.create({ job_id: active.id, request_id: crypto.randomUUID(),
            resume_version_id: version?.id ?? null, channel: field(data, 'channel'),
            job_match_id: match && (!version || version.content_id === match.content_id) ? match.id : undefined })
          applied()
        })
      }}>
        <div className="career-grid">
          <label>投递简历版本<select name="version"><option value="">稍后关联</option>
            {versions.filter((item) => item.target_job_id == null || item.target_job_id === active.id)
              .map((item) => <option key={item.id} value={item.id}>{item.version_name} v{item.version_number}</option>)}
          </select></label>
          <label>投递渠道<input name="channel" maxLength={150} /></label>
        </div>
        <div><button className="button button-filled" disabled={busy}>添加至投递看板</button></div>
      </form>}
    </Panel>}
  </>
}
