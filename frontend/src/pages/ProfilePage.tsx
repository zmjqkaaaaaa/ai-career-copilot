import { Feedback } from '../components/common/Feedback'
import { useState } from 'react'
import type { FormEvent } from 'react'
import { useAuth } from '../hooks/AuthProvider'
import { errorMessage } from '../services/api'
import type { Experience, ProfileInput } from '../services/profile'

const identityFields = [
  ['real_name', '姓名', 100],
  ['undergraduate_school', '本科院校', 150],
  ['undergraduate_major', '本科专业', 150],
  ['undergraduate_degree', '本科学历', 80],
  ['graduate_school', '研究生院校', 150],
  ['graduate_major', '研究生专业', 150],
  ['target_position', '目标岗位', 150],
] as const

type ExperienceFields = { key: number; value: Experience }

function ExperienceEditor({ title, items, setItems }: {
  title: string
  items: ExperienceFields[]
  setItems: (items: ExperienceFields[]) => void
}) {
  function update(key: number, field: keyof Experience, value: string) {
    setItems(items.map((item) => item.key === key ? { key, value: { ...item.value, [field]: value } } : item))
  }

  return (
    <fieldset className="experience-list">
      <legend>{title}</legend>
      {items.map(({ key, value }, index) => (
        <div className="experience-entry" key={key}>
          <label>{title} {index + 1} 名称<input required maxLength={150} value={value.title} onChange={(event) => update(key, 'title', event.target.value)} /></label>
          <label>{title} {index + 1} 说明<textarea rows={3} maxLength={2000} value={value.description} onChange={(event) => update(key, 'description', event.target.value)} /></label>
          <button className="button button-outline" type="button" onClick={() => setItems(items.filter((item) => item.key !== key))}>移除第 {index + 1} 项{title}</button>
        </div>
      ))}
      <button className="button button-outline" type="button" disabled={items.length >= 20} onClick={() => setItems([
        ...items, { key: Math.max(-1, ...items.map((item) => item.key)) + 1, value: { title: '', description: '' } },
      ])}>添加{title}</button>
    </fieldset>
  )
}

function ProfileForm({ initial, save }: { initial: ProfileInput | null; save: (input: ProfileInput) => Promise<void> }) {
  const [internships, setInternships] = useState(() => (initial?.internship_experience ?? []).map((value, key) => ({ key, value })))
  const [projects, setProjects] = useState(() => (initial?.project_experience ?? []).map((value, key) => ({ key, value })))
  const [saving, setSaving] = useState(false)
  const [feedback, setFeedback] = useState<{ kind: 'error' | 'success'; text: string } | null>(null)

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setFeedback(null)
    const form = new FormData(event.currentTarget)
    const text = (key: string) => String(form.get(key) ?? '').trim()
    const list = (key: string) => text(key).split(/[，,、\n]+/).map((value) => value.trim()).filter(Boolean)
    const year = text('graduation_year')
    const inputs = Object.fromEntries(identityFields.map(([field]) => [field, text(field) || null])) as Pick<ProfileInput, (typeof identityFields)[number][0]>
    const industries = list('interested_industries')
    const skills = list('skills')
    if ([industries, skills].some((values) => values.length > 30 || values.some((value) => value.length > 80))) {
      setFeedback({ kind: 'error', text: '兴趣行业和技能各最多 30 项，每项最多 80 个字符。' })
      return
    }
    if ([...internships, ...projects].some(({ value }) => !value.title.trim())) {
      setFeedback({ kind: 'error', text: '请输入每项经历的名称。' })
      return
    }
    setSaving(true)
    try {
      await save({
        ...inputs,
        graduation_year: year ? Number(year) : null,
        interested_industries: industries,
        skills,
        internship_experience: internships.map(({ value }) => value),
        project_experience: projects.map(({ value }) => value),
      })
      setFeedback({ kind: 'success', text: '个人档案已保存。' })
    } catch (failure) {
      setFeedback({ kind: 'error', text: errorMessage(failure) })
    } finally {
      setSaving(false)
    }
  }

  return (
    <form className="account-form profile-form" aria-busy={saving} onSubmit={submit}>
      <fieldset disabled={saving}>
        <div className="profile-fields">
          {identityFields.map(([name, label, length]) => (
            <label key={name}>{label}<input name={name} defaultValue={initial?.[name] ?? ''} maxLength={length} /></label>
          ))}
          <label>预计毕业年份<input name="graduation_year" type="number" min={1900} max={2100} step={1} defaultValue={initial?.graduation_year ?? ''} /></label>
          <label>兴趣行业<input name="interested_industries" defaultValue={initial?.interested_industries.join('，') ?? ''} placeholder="用逗号或顿号分隔" /></label>
          <label>技能<input name="skills" defaultValue={initial?.skills.join('，') ?? ''} placeholder="用逗号或顿号分隔" /></label>
        </div>
        <ExperienceEditor title="实习经历" items={internships} setItems={setInternships} />
        <ExperienceEditor title="项目经历" items={projects} setItems={setProjects} />
      </fieldset>
      {feedback && <Feedback kind={feedback.kind}>{feedback.text}</Feedback>}
      <button className="button button-filled" disabled={saving}>{saving ? '正在保存…' : '保存档案'}</button>
    </form>
  )
}

export function ProfilePage() {
  const { profile, reloadProfile, saveProfile } = useAuth()

  return (
    <section className="surface profile-card" aria-labelledby="profile-title">
      <h1 id="profile-title">个人档案</h1>
      {profile.state === 'loading' && <Feedback kind="loading">正在读取档案…</Feedback>}
      {profile.state === 'error' && <Feedback kind="error" retry={reloadProfile}>{profile.message}</Feedback>}
      {profile.state === 'missing' && <Feedback kind="empty">尚未创建档案。填写你想记录的信息即可保存。</Feedback>}
      {(profile.state === 'missing' || profile.state === 'ready') &&
        <ProfileForm initial={profile.state === 'ready' ? profile.data : null} save={saveProfile} />}
    </section>
  )
}
