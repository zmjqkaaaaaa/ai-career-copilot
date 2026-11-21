import { useState } from 'react'
import type { ChangeEvent } from 'react'
import type { Competitor, Opportunity, PainRecord, Session } from '../../services/discovery'

export const evidenceLabels: Record<string, string> = { experience:'亲身经历', observation:'观察', hearsay:'转述', market_inference:'市场推断' }

export function SessionEditor({ session, onSave, disabled }: { session: Session; onSave:(value: Session) => void; disabled: boolean }) {
  const [value, set] = useState(session)
  return <form className="account-form" onSubmit={(event) => { event.preventDefault(); onSave(value) }}>
    <div className="profile-fields">
      <label>会话名称<input value={value.title} required maxLength={180} onChange={(e) => set({ ...value, title:e.target.value })} /></label>
      <label>教学模式<select value={value.mode} onChange={(e) => set({ ...value, mode:e.target.value === 'guided' ? 'guided' : 'assisted' })}><option value="guided">引导模式</option><option value="assisted">辅助模式</option></select></label>
      <label>探索方向<input value={value.direction ?? ''} maxLength={180} onChange={(e) => set({ ...value, direction:e.target.value || null })} /></label>
      <label>每周可投入小时<input type="number" min={1} max={80} value={value.weekly_hours ?? ''} onChange={(e) => set({ ...value, weekly_hours:Number(e.target.value) || null })} /></label>
    </div><button className="button button-outline" disabled={disabled}>保存探索偏好</button>
  </form>
}

export function PainEditor({ item, onSave, disabled }: { item: PainRecord; onSave: (value: PainRecord) => void; disabled: boolean }) {
  const [record, set] = useState(item)
  const [newEvidence, setEvidence] = useState('')
  const [kind, setKind] = useState('observation')
  const pain = record.data
  const update = (field: string) => (e: ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>) =>
    set((old) => ({ ...old, data: { ...old.data, [field]: e.target.value || null } }))
  return <form className="account-form mt-3" onSubmit={(event) => {
    event.preventDefault()
    const evidence = newEvidence.trim() ? [...pain.evidence, { kind, detail: newEvidence.trim() }] : pain.evidence
    onSave({ ...record, data: { ...pain, evidence } })
  }}>
    <div className="profile-fields">
      <label>痛点名称<input required maxLength={180} value={pain.pain_point_name} onChange={update('pain_point_name')} /></label>
      <label>目标用户<input required maxLength={180} value={pain.target_user} onChange={update('target_user')} /></label>
      <label>使用场景<textarea required maxLength={1200} value={pain.scenario} onChange={update('scenario')} /></label>
      <label>用户问题<textarea required maxLength={1200} value={pain.user_problem} onChange={update('user_problem')} /></label>
      <label>现有解决方式<textarea maxLength={1200} value={pain.current_solution ?? ''} onChange={update('current_solution')} /></label>
      <label>发生频率<input maxLength={180} value={pain.frequency ?? ''} onChange={update('frequency')} /></label>
      <label>严重度<input maxLength={180} value={pain.severity ?? ''} onChange={update('severity')} /></label>
      <label>验证状态<select value={pain.validation_status} onChange={update('validation_status')}><option value="hypothesis">待验证假设</option><option value="user_reviewed">用户已核对</option><option value="interview_reported">已补录访谈转述</option></select></label>
    </div>
    <div><strong>现有证据</strong>{pain.evidence.map((e, index) => <blockquote key={index}>{evidenceLabels[e.kind]} · {e.detail}</blockquote>)}</div>
    <label>补充证据类型<select value={kind} onChange={(e) => setKind(e.target.value)}>{Object.entries(evidenceLabels).map(([key, title]) => <option key={key} value={key}>{title}</option>)}</select></label>
    <label>补充证据<textarea maxLength={1200} value={newEvidence} onChange={(e) => setEvidence(e.target.value)} /></label>
    {pain.interview_questions.length > 0 && <div><strong>访谈提纲 · {pain.interview_target}</strong><ul>{pain.interview_questions.map((question) => <li key={question}>{question}</li>)}</ul><p>{pain.demand_signal}</p></div>}
    <button className="button button-filled" disabled={disabled}>保存痛点</button>
  </form>
}

export function CompetitorEditor({ value, onSave, disabled }: { value: Competitor; onSave:(data: Competitor) => void; disabled: boolean }) {
  const [name, set] = useState(value.product_name)
  return <form className="account-form" onSubmit={(e) => { e.preventDefault(); onSave({ ...value, product_name: name }) }}>
    <label>竞品名称<input value={name} required maxLength={180} onChange={(e) => set(e.target.value)} /></label>
    <button className="button button-outline" disabled={disabled}>保存竞品名称</button>
  </form>
}

export function OpportunityEditor({ item, onSave, disabled }: { item: Opportunity; onSave: (body: unknown) => void; disabled: boolean }) {
  const [validation, setValidation] = useState(item.data.validation_plan)
  const [notes, setNotes] = useState(item.data.feasibility)
  return <form className="account-form" onSubmit={(e) => {
    e.preventDefault()
    const { ratings, risks, differentiation } = item.data
    onSave({ ratings: ratings.map(({ dimension, rating, reason, basis, references }) => ({ dimension, rating, reason, basis, references })),
      risks, differentiation, feasibility: notes, validation_plan: validation })
  }}>
    <label>可行性判断<textarea maxLength={1200} required value={notes} onChange={(e) => setNotes(e.target.value)} /></label>
    <label>验证方案<textarea maxLength={1200} required value={validation} onChange={(e) => setValidation(e.target.value)} /></label>
    <button className="button button-outline" disabled={disabled}>保存机会分析版本</button>
  </form>
}
