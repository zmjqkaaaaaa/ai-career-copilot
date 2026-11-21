import { useEffect, useState } from 'react'
import { Link } from 'react-router'
import { applications, field, statuses, type Application, type ResumeVersion, type Status, type StatusEvent } from '../../services/applications'
import { dateLabel, JobName, Panel, showFailure, type Run } from './shared'

const statusesList = Object.keys(statuses) as Status[]
const editable = [
  ['channel', '渠道'], ['contact', '联系人（选填）'], ['notes', '投递备注'],
  ['next_action', '下一步行动'], ['feedback', '面试反馈'], ['rejection_reason', '拒绝原因'],
] as const

export function Pipeline({ columns, versions, selected, select, refresh, run, error, busy }: {
  columns: Record<Status, Application[]> | undefined; versions: ResumeVersion[]; selected: number | null;
  select: (id: number) => void; refresh: number; run: Run; error: (message: string) => void; busy: boolean
}) {
  const [detail, setDetail] = useState<Application | null>(null)
  const [history, setHistory] = useState<StatusEvent[]>([])
  const [status, setStatus] = useState<Status>('wishlist')
  const [dragged, setDragged] = useState<number | null>(null)
  const current = detail?.id === selected ? detail : null

  useEffect(() => {
    if (!selected) return
    let ignore = false
    Promise.all([applications.detail(selected), applications.history(selected)]).then(([record, events]) => {
      if (!ignore) { setDetail(record); setStatus(record.current_status); setHistory(events) }
    }).catch((failure) => { if (!ignore) showFailure(failure, error) })
    return () => { ignore = true }
  }, [selected, refresh, error])

  function move(record: Application, into: Status, note?: string) {
    if (record.current_status === into) return
    void run(async () => { await applications.move(record, into, note) })
  }

  return <>
    <Panel title="投递管理看板">
      <p>拖动投递卡片，或在详情中选择状态。首次进入已投递或后续阶段时，系统记录投递时间。</p>
      <div className="application-board" aria-label="投递看板">
        {statusesList.map((stage) => <section key={stage} onDragOver={(event) => {
          if (dragged !== null && !busy) event.preventDefault()
        }} onDrop={(event) => {
          event.preventDefault()
          const record = Object.values(columns ?? {}).flat().find((row) => row.id === dragged)
          setDragged(null)
          if (record && !busy) move(record, stage)
        }}>
          <h3>{statuses[stage]} <span>{columns?.[stage].length ?? 0}</span></h3>
          {columns?.[stage].map((row) => <article key={row.id} draggable={!busy}
            onDragStart={(event) => { event.dataTransfer.setData('text/plain', String(row.id)); setDragged(row.id) }}
            onDragEnd={() => setDragged(null)}>
            <button className="application-link" onClick={() => select(row.id)}><JobName row={row} /></button>
            <p>{dateLabel(row.applied_at)}</p>
            {row.next_action && <p>{row.next_action}</p>}
          </article>)}
        </section>)}
      </div>
    </Panel>
    {current && <Panel title={`${current.job.position} · 投递详情`}>
      <p><JobName row={current} /> · {statuses[current.current_status]}</p>
      <div className="flex flex-wrap gap-2">
        <Link className="button button-outline" to={`?tab=positions&job=${current.job_id}`}>查看岗位</Link>
        <Link className="button button-outline" to={`?tab=schedules&application=${current.id}`}>查看或添加面试</Link>
        {current.resume_version_id && <Link className="button button-outline" to={`?tab=versions&version=${current.resume_version_id}`}>查看投递简历</Link>}
      </div>
      <form key={`status-${current.id}-${current.revision}`} className="account-form" onSubmit={(event) => {
        event.preventDefault()
        const data = new FormData(event.currentTarget)
        move(current, status, field(data, 'note') ?? undefined)
      }}>
        <div className="career-grid">
          <label>更新投递状态<select value={status} onChange={(event) => setStatus(event.target.value as Status)}>
            {statusesList.map((stage) => <option key={stage} value={stage} disabled={stage === 'wishlist' && Boolean(current.applied_at)}>{statuses[stage]}</option>)}
          </select></label>
          <label>变更说明<input name="note" maxLength={1000} /></label>
        </div>
        <div><button className="button button-filled" disabled={busy || status === current.current_status}>保存状态</button></div>
      </form>
      <form key={`edit-${current.id}-${current.revision}`} className="account-form" onSubmit={(event) => {
        event.preventDefault()
        const data = new FormData(event.currentTarget)
        void run(async () => {
          await applications.edit(current.id, {
            revision: current.revision, ...Object.fromEntries(editable.map(([key]) => [key, field(data, key)])),
            valid_submission: data.has('valid'),
            ...(data.has('resume') ? { resume_version_id: Number(field(data, 'resume')) || null } : {}),
            ...(field(data, 'applied_at') ? { applied_at: new Date(field(data, 'applied_at')!).toISOString() } : {}),
          })
        })
      }}>
        <div className="career-grid">
          {editable.map(([key, label]) => <label key={key}>{label}<input name={key} defaultValue={current[key] ?? ''}
            maxLength={key === 'channel' || key === 'contact' ? 150 : 1000} /></label>)}
          {(!current.applied_at || current.resume_version_id == null) && <label>关联简历版本<select name="resume" defaultValue={current.resume_version_id ?? ''}>
            <option value="">暂未关联</option>
            {versions.filter((row) => !row.target_job_id || row.target_job_id === current.job_id).map((row) =>
              <option key={row.id} value={row.id}>{row.version_name} v{row.version_number}</option>)}
          </select></label>}
          {current.applied_at && <label>修正投递时间<input type="datetime-local" name="applied_at" /></label>}
        </div>
        <label className="application-check"><input type="checkbox" name="valid" defaultChecked={current.valid_submission} />计入有效投递</label>
        <div><button className="button button-outline" disabled={busy}>保存投递详情</button></div>
      </form>
      <details open><summary>状态历史</summary><ul className="application-list">{history.map((row) =>
        <li key={row.id}>{row.previous_status ? `${statuses[row.previous_status]} → ` : ''}{statuses[row.new_status]} · {dateLabel(row.changed_at)}
          {row.notes && <p>{row.notes}</p>}</li>)}</ul></details>
    </Panel>}
  </>
}
