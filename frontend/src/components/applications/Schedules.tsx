import { useEffect, useState } from 'react'
import { Link } from 'react-router'
import { applications, field, statuses, type Application, type Schedule } from '../../services/applications'
import { appointmentTime, Panel, showFailure, type Run } from './shared'

const outcomes = { scheduled: '已安排', pending: '结果待定', passed: '通过', failed: '未通过', cancelled: '已取消' }
const formats = { online: '视频面试', onsite: '现场面试', phone: '电话面试', other: '其他' }
const rounds = { interview_1: statuses.interview_1, interview_2: statuses.interview_2, hr_interview: statuses.hr_interview, other: '其他轮次' }

function zonedParts(value: string, timezone: string) {
  return Object.fromEntries(new Intl.DateTimeFormat('en-CA', {
    timeZone: timezone, year: 'numeric', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit', hourCycle: 'h23', timeZoneName: 'longOffset',
  }).formatToParts(new Date(value)).map((item) => [item.type, item.value]))
}
function formatInput(value: string, timezone: string) {
  const parts = zonedParts(value, timezone)
  return `${parts.year}-${parts.month}-${parts.day}T${parts.hour}:${parts.minute}`
}
function shiftMonth(month: string, change: number) {
  const [year, index] = month.split('-').map(Number)
  const next = new Date(Date.UTC(year, index - 1 + change, 1))
  return next.toISOString().slice(0, 7)
}

export function Schedules({ records, target, selectedId, run, error, refresh, busy }: {
  records: Application[]; target: number | null; selectedId: number | null; run: Run; error: (message: string) => void; refresh: number; busy: boolean
}) {
  const [schedules, setSchedules] = useState<Schedule[]>([])
  const [editing, setEditing] = useState<Schedule | null>(null)
  const [selected, setSelected] = useState<number | null>(selectedId)
  const localZone = Intl.DateTimeFormat().resolvedOptions().timeZone
  const [month, setMonth] = useState(() => formatInput(new Date().toISOString(), localZone).slice(0, 7))
  const shown = schedules.filter((row) => (!target || row.application_id === target)
    && formatInput(row.scheduled_at, row.timezone).startsWith(month))
  const selectedSchedule = schedules.find((row) => row.id === selected)
  const listLabel = target ? records.find((row) => row.id === target)?.job.position : undefined
  const grouped = new Map<number, Schedule[]>()
  for (const row of shown) {
    const day = Number(formatInput(row.scheduled_at, row.timezone).slice(8, 10))
    grouped.set(day, [...(grouped.get(day) ?? []), row])
  }
  const [year, monthIndex] = month.split('-').map(Number)
  const firstDay = (new Date(Date.UTC(year, monthIndex - 1, 1)).getUTCDay() + 6) % 7
  const days = new Date(Date.UTC(year, monthIndex, 0)).getUTCDate()

  useEffect(() => {
    let ignore = false
    applications.schedules().then((data) => { if (!ignore) setSchedules(data) })
      .catch((failure) => { if (!ignore) showFailure(failure, error) })
    return () => { ignore = true }
  }, [refresh, error])

  useEffect(() => {
    const row = schedules.find((item) => item.id === selectedId)
    if (row) {
      setSelected(row.id)
      setMonth(formatInput(row.scheduled_at, row.timezone).slice(0, 7))
    }
  }, [schedules, selectedId])

  const initialOffset = editing ? zonedParts(editing.scheduled_at, editing.timezone).timeZoneName.slice(3) : ''
  return <>
    <Panel title={listLabel ? `面试日程 · ${listLabel}` : '面试日程'}>
      {target && <Link className="application-link" to="?tab=schedules">查看全部面试</Link>}
      <div className="flex flex-wrap items-center gap-2">
        <button className="button button-outline" onClick={() => setMonth(shiftMonth(month, -1))}>上个月</button>
        <label>日历月份 <input aria-label="日历月份" type="month" value={month} onChange={(event) => event.target.value && setMonth(event.target.value)} /></label>
        <button className="button button-outline" onClick={() => setMonth(shiftMonth(month, 1))}>下个月</button>
      </div>
      <div className="application-calendar">
        {['周一','周二','周三','周四','周五','周六','周日'].map((day) => <strong key={day}>{day}</strong>)}
        {Array.from({ length: firstDay }, (_, index) => <span key={`empty-${index}`} />)}
        {Array.from({ length: days }, (_, index) => <div key={index}>
          {index + 1}
          {grouped.get(index + 1)?.map((row) => <button key={row.id} className="application-link" onClick={() => setSelected(row.id)}>
            {row.position}
          </button>)}
        </div>)}
      </div>
      <ul className="application-list">{shown.map((row) => <li key={row.id}>
        <button className="application-link" onClick={() => setSelected(row.id)}>{row.company ?? '公司未知'} · {row.position}</button>
        <span>{appointmentTime(row)} · {row.timezone} · {outcomes[row.result as keyof typeof outcomes]}</span>
      </li>)}
      {!shown.length && <li>本月暂无面试。</li>}</ul>
    </Panel>
    {selectedSchedule && <Panel title={`${selectedSchedule.position} · 面试详情`}>
      <p>{appointmentTime(selectedSchedule)} · {selectedSchedule.timezone} · {selectedSchedule.duration} 分钟</p>
      <p>{rounds[selectedSchedule.interview_round as keyof typeof rounds]} · {formats[selectedSchedule.interview_type as keyof typeof formats]} · {outcomes[selectedSchedule.result as keyof typeof outcomes]}</p>
      {selectedSchedule.location_or_url && <p>地点或链接 {selectedSchedule.location_or_url}</p>}
      {selectedSchedule.preparation_notes && <p>准备事项 {selectedSchedule.preparation_notes}</p>}
      {selectedSchedule.retrospective && <p>面试复盘 {selectedSchedule.retrospective}</p>}
      <div className="flex flex-wrap gap-2">
        <Link className="button button-filled" to={`/interview-practice?schedule=${selectedSchedule.id}`}>进入模拟面试</Link>
        <button className="button button-outline" onClick={() => setEditing(selectedSchedule)}>编辑日程或结果</button>
        <Link className="button button-outline" to={`?tab=board&application=${selectedSchedule.application_id}`}>查看关联投递</Link>
      </div>
    </Panel>}
    <Panel title={editing ? '编辑面试日程' : '添加面试日程'}>
      {!records.length ? <Link className="application-link" to="?tab=positions">先添加一条投递记录</Link>
        : <form key={`${editing?.id ?? 'new'}-${target ?? ''}`} className="account-form" onSubmit={(event) => {
          event.preventDefault()
          const data = new FormData(event.currentTarget)
          const timezone = field(data, 'timezone') ?? localZone
          const localTime = field(data, 'start')!
          const offset = field(data, 'offset')
          if (!offset && timezone !== localZone) { error('请为所选时区填写 UTC 偏移，例如 +08:00'); return }
          const parsedLocal = new Date(localTime)
          if (!offset && (!Number.isFinite(+parsedLocal) || formatInput(parsedLocal.toISOString(), localZone) !== localTime)) {
            error('该时间在所选时区不可用，请重新选择。'); return
          }
          const localOffset = !offset ? zonedParts(parsedLocal.toISOString(), localZone).timeZoneName.slice(3) : null
          const payload = {
            scheduled_at: `${localTime}:00${offset || localOffset || '+00:00'}`, timezone,
            duration: Number(field(data, 'duration')), interview_round: field(data, 'round'),
            interview_type: field(data, 'type'), location_or_url: field(data, 'location'),
            preparation_notes: field(data, 'notes'), result: field(data, 'result'),
            retrospective: field(data, 'retrospective'),
          }
          void run(async () => {
            const row = await applications.saveSchedule(editing ? { ...payload, revision: editing.revision }
              : { ...payload, request_id: crypto.randomUUID(), application_id: Number(field(data, 'application')) }, editing?.id)
            setEditing(null); setSelected(row.id); setMonth(formatInput(row.scheduled_at, row.timezone).slice(0,7))
          })
        }}>
          <div className="career-grid">
            {!editing && <label>关联投递<select name="application" required defaultValue={target ?? ''}>
              <option value="">请选择</option>
              {records.map((row) => <option key={row.id} value={row.id}>{row.job.company ?? '公司未知'} · {row.job.position}</option>)}
            </select></label>}
            <label>面试开始时间<input name="start" type="datetime-local" required
              defaultValue={editing ? formatInput(editing.scheduled_at, editing.timezone) : undefined} /></label>
            <label>时区<input name="timezone" required maxLength={80} defaultValue={editing?.timezone ?? localZone} placeholder="Asia/Shanghai" /></label>
            <label>UTC 偏移<input name="offset" placeholder="+08:00，本机时区可留空" pattern="[+-][0-9]{2}:[0-9]{2}" defaultValue={initialOffset} /></label>
            <label>时长（分钟）<input name="duration" type="number" min={5} max={480} defaultValue={editing?.duration ?? 60} required /></label>
            <label>面试轮次<select name="round" defaultValue={editing?.interview_round}>
              {Object.entries(rounds).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
            </select></label>
            <label>面试形式<select name="type" defaultValue={editing?.interview_type}>
              {Object.entries(formats).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
            </select></label>
            <label>面试结果<select name="result" defaultValue={editing?.result}>
              {Object.entries(outcomes).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
            </select></label>
            <label>地点或会议链接<input name="location" maxLength={1000} defaultValue={editing?.location_or_url ?? ''} /></label>
          </div>
          <label>准备事项<textarea name="notes" maxLength={1000} defaultValue={editing?.preparation_notes ?? ''} /></label>
          <label>面试复盘<textarea name="retrospective" maxLength={1000} defaultValue={editing?.retrospective ?? ''} /></label>
          <div className="flex flex-wrap gap-2">
            <button className="button button-filled" disabled={busy}>保存面试日程</button>
            {editing && <button className="button button-outline" type="button" onClick={() => setEditing(null)}>取消编辑</button>}
          </div>
        </form>}
    </Panel>
  </>
}
