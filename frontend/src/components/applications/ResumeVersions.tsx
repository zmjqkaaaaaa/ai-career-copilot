import { useEffect, useState } from 'react'
import { Link } from 'react-router'
import { applications, field, type Position, type ResumePreview, type ResumeVersion } from '../../services/applications'
import { jobsApi, type Version } from '../../services/jobs'
import { Panel, showFailure, type Run } from './shared'

export function ResumeVersions({ target, selected, versions, run, error, busy }: {
  target: number | null; selected: number | null; versions: ResumeVersion[]; run: Run; error: (message: string) => void; busy: boolean
}) {
  const [candidates, setCandidates] = useState<Version[]>([])
  const [positions, setPositions] = useState<Position[]>([])
  const [contentId, setContentId] = useState('')
  const [jobId, setJobId] = useState(String(target ?? ''))
  const [preview, setPreview] = useState<ResumePreview | null>(null)
  const [numbers, setNumbers] = useState<number[]>([])
  const [optimizations, setOptimizations] = useState<Record<number, number>>({})
  const [current, setCurrent] = useState<ResumeVersion | null>(null)
  const [before, setBefore] = useState<ResumeVersion | null>(null)
  const [editing, setEditing] = useState<ResumeVersion | null>(null)

  useEffect(() => {
    let ignore = false
    Promise.all([jobsApi.versions(), applications.positions(), target ? applications.position(target) : null])
      .then(([sources, jobs, selected]) => {
        if (!ignore) {
          setCandidates(sources); setContentId(String(sources[0]?.id ?? ''))
          setPositions(selected && !jobs.some((row) => row.id === selected.id) ? [selected, ...jobs] : jobs)
        }
      }).catch((failure) => { if (!ignore) showFailure(failure, error) })
    return () => { ignore = true }
  }, [error, target])

  useEffect(() => {
    if (!selected) return
    let ignore = false
    applications.version(selected).then((row) => { if (!ignore) setCurrent(row) })
      .catch((failure) => { if (!ignore) showFailure(failure, error) })
    return () => { ignore = true }
  }, [selected, error])

  function move(index: number, step: number) {
    const next = [...numbers]
    const other = index + step
    const item = next[index]
    next[index] = next[other]
    next[other] = item
    setNumbers(next)
  }

  function start(source: number, job: number | null, previous?: ResumeVersion) {
    void run(async () => {
      const data = await applications.versionPreview({ content_id: source, target_job_id: job })
      setPreview(data); setEditing(previous ?? null)
      setNumbers((previous?.content ?? data.blocks).map((block) => block.number))
      setOptimizations(Object.fromEntries((previous?.content ?? []).flatMap((block) =>
        block.optimization_id ? [[block.number, block.optimization_id]] : [])))
    }, false)
  }

  return <>
    <Panel title="简历版本中心">
      <p>从已确认简历选择段落、调整顺序或应用已确认的优化。保存后保留各版本的内容。</p>
      <form className="account-form" onSubmit={(event) => { event.preventDefault(); start(Number(contentId), Number(jobId) || null) }}>
        <div className="career-grid">
          <label>原始已确认简历<select required value={contentId} onChange={(event) => { setContentId(event.target.value); setPreview(null) }}>
            <option value="">请选择</option>{candidates.map((row) => <option key={row.id} value={row.id}>{row.original_filename} v{row.version}</option>)}
          </select></label>
          <label>定向岗位<select value={jobId} onChange={(event) => { setJobId(event.target.value); setPreview(null) }}>
            <option value="">通用版</option>{positions.map((row) => <option key={row.id} value={row.id}>{row.position_name} · {row.company_name ?? '公司未知'}</option>)}
          </select></label>
        </div>
        {!candidates.length && <Link className="application-link" to="/career-profile">上传并确认一份简历</Link>}
        <div><button className="button button-filled" disabled={busy || !contentId}>预览候选段落</button></div>
      </form>
      <ul className="application-list">{versions.map((row) => <li key={row.id}>
        <button className="application-link" onClick={() => void run(async () => {
          setCurrent(await applications.version(row.id)); setBefore(null)
        }, false)}>{row.version_name} v{row.version_number}</button>
        <span>{row.target_position ?? '通用版'} · {row.change_summary}</span>
      </li>)}
      {!versions.length && <li>暂无简历版本。</li>}</ul>
    </Panel>
    {preview && <Panel title={editing ? `从 v${editing.version_number} 创建新版本` : '制作定向简历'}>
      {preview.recommendations && <div><h3>此 JD 的 AI 建议</h3>
        <p>{preview.recommendations.rationale}</p>
        <ul>{preview.recommendations.resume_focus.map((item) => <li key={item}>{item}</li>)}</ul></div>}
      {!!preview.gaps.length && <p>需要核对的差距：{preview.gaps.join('、')}</p>}
      {!preview.recommendations && jobId && <Link className="application-link" to={`/job-matching?job=${jobId}`}>去岗位匹配生成针对 JD 的优化建议</Link>}
      <form key={editing?.id ?? `${contentId}-${jobId}`} className="account-form" onSubmit={(event) => {
        event.preventDefault()
        const values = new FormData(event.currentTarget)
        void run(async () => {
          const body = { request_id: crypto.randomUUID(), version_name: field(values, 'version_name'),
            change_summary: field(values, 'change_summary'), block_numbers: numbers,
            optimization_ids: numbers.flatMap((number) => optimizations[number] ? [optimizations[number]] : []), confirmed: true }
          const saved = await applications.saveVersion(editing ? body : {
            ...body, content_id: Number(contentId), target_job_id: Number(jobId) || null,
          }, editing?.id)
          setCurrent(saved); setBefore(null); setPreview(null)
        })
      }}>
        <div className="career-grid">
          <label>版本名称<input name="version_name" required maxLength={150} defaultValue={editing?.version_name} /></label>
          <label>修改原因<input name="change_summary" required maxLength={1000} /></label>
        </div>
        <ul className="application-list">
          {numbers.map((number, index) => {
            const original = preview.blocks.find((block) => block.number === number)
            const choices = preview.optimizations.filter((row) => row.number === number)
            return <li key={number}>
              <p>{choices.find((row) => row.id === optimizations[number])?.text ?? original?.text}</p>
              {choices.length > 0 && <label>段落 {number} 的确认优化<select value={optimizations[number] ?? ''}
                onChange={(event) => setOptimizations({ ...optimizations, [number]: Number(event.target.value) })}>
                <option value="">使用原文</option>{choices.map((row) => <option key={row.id} value={row.id}>{row.reason}</option>)}
              </select></label>}
              <div className="flex flex-wrap gap-2">
                <button type="button" className="button button-outline" disabled={!index} onClick={() => move(index, -1)}>上移段落 {number}</button>
                <button type="button" className="button button-outline" disabled={index === numbers.length - 1} onClick={() => move(index, 1)}>下移段落 {number}</button>
                <button type="button" className="button button-outline" onClick={() => setNumbers(numbers.filter((item) => item !== number))}>移除段落 {number}</button>
              </div>
            </li>
          })}
        </ul>
        {preview.blocks.filter((block) => !numbers.includes(block.number)).map((block) =>
          <button type="button" className="application-link" key={block.number} onClick={() => setNumbers([...numbers, block.number])}>
            恢复段落 {block.number} · {block.text.slice(0, 65)}
          </button>)}
        <label className="application-check"><input type="checkbox" required />我确认这些段落准确反映我的经历</label>
        <div className="flex flex-wrap gap-2">
          <button className="button button-filled" disabled={busy || !numbers.length}>确认并保存版本</button>
          <button className="button button-outline" type="button" onClick={() => setPreview(null)}>取消</button>
        </div>
      </form>
    </Panel>}
    {current && <Panel title={`${current.version_name} v${current.version_number}`}>
      <p>修改记录 · {current.change_summary}</p>
      <div className="flex flex-wrap gap-2">
        <button className="button button-outline" disabled={!current.content_id || versions.some((row) => row.previous_id === current.id)}
          onClick={() => current.content_id && start(current.content_id, current.target_job_id, current)}>创建后续版本</button>
        {current.previous_id && <button className="button button-outline" onClick={() => void run(async () => {
          setBefore(await applications.version(current.previous_id!))
        }, false)}>与上一版本对比</button>}
      </div>
      <div className="career-grid">
        {before && <div><h3>{before.version_name} v{before.version_number}</h3>{before.content?.map((block) => <p key={block.number}>{block.text}</p>)}</div>}
        <div>{current.content?.map((block) => <p key={block.number}>{block.text}</p>)}</div>
      </div>
    </Panel>}
  </>
}
