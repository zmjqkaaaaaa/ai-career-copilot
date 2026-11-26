import { Feedback } from '../components/common/Feedback'
import { useEffect, useState } from 'react'
import { Link } from 'react-router'
import type { FormEvent } from 'react'
import { useAuth } from '../hooks/AuthProvider'
import { errorMessage } from '../services/api'
import { profileApi, type Experience, type ProfileInput, type ResumeDraft } from '../services/profile'

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

function mergeDraft(saved: ProfileInput | null, draft: ProfileInput): ProfileInput {
  if (!saved) return draft
  return {
    ...saved,
    undergraduate_school: saved.undergraduate_school ?? draft.undergraduate_school,
    undergraduate_major: saved.undergraduate_major ?? draft.undergraduate_major,
    undergraduate_degree: saved.undergraduate_degree ?? draft.undergraduate_degree,
    graduate_school: saved.graduate_school ?? draft.graduate_school,
    graduate_major: saved.graduate_major ?? draft.graduate_major,
    graduation_year: saved.graduation_year ?? draft.graduation_year,
    skills: saved.skills.length ? saved.skills : draft.skills,
    internship_experience: saved.internship_experience.length ? saved.internship_experience : draft.internship_experience,
    project_experience: saved.project_experience.length ? saved.project_experience : draft.project_experience,
  }
}

export function ProfilePage() {
  const { account, profile, reloadProfile, saveProfile } = useAuth()
  const userId = account?.id
  const [resume, setResume] = useState<{ userId: number; draft: ResumeDraft | null; error?: string }>()
  const [draftCheck, setDraftCheck] = useState(0)
  useEffect(() => {
    if (userId === undefined) return
    const controller = new AbortController()
    profileApi.resumeDraft(controller.signal).then((draft) => {
      if (!controller.signal.aborted) setResume({ userId, draft })
    }).catch((failure: unknown) => {
      if (!controller.signal.aborted) setResume({ userId, draft: null, error: errorMessage(failure) })
    })
    return () => controller.abort()
  }, [userId, draftCheck])
  const resumeState = resume?.userId === userId ? resume : undefined
  const draft = resumeState?.draft
  const saved = profile.state === 'ready' ? profile.data : null

  return (
    <section className="surface profile-card" aria-labelledby="profile-title">
      <h1 id="profile-title">个人档案</h1>
      {profile.state === 'loading' && <Feedback kind="loading">正在读取档案…</Feedback>}
      {profile.state === 'error' && <Feedback kind="error" retry={reloadProfile}>{profile.message}</Feedback>}
      {!resumeState && profile.state !== 'error' && <Feedback kind="loading">正在读取已确认的简历…</Feedback>}
      {resumeState?.error && <Feedback kind="error" retry={() => {
        setResume(undefined)
        setDraftCheck((value) => value + 1)
      }}>{resumeState.error}</Feedback>}
      {draft && <div className="career-detail">
        <p>已从 <Link className="text-brand underline" to={`/career-profile?resume=${draft.resume_id}&content=${draft.content_id}`}>
          {draft.filename} · 第 {draft.version} 版</Link> 带入可识别的空白字段。核对后点击「保存档案」即可。</p>
        {draft.education.length > 0 && <details><summary>查看简历教育经历</summary>
          {draft.education.map((quote, index) => <p className="whitespace-pre-wrap" key={index}>{quote}</p>)}
        </details>}
      </div>}
      {resumeState && !draft && !resumeState.error && profile.state === 'missing' && <Feedback kind="empty">
        <Link className="text-brand underline" to="/career-profile">在职业画像确认一份简历</Link> 后可自动带入，也可直接填写。
      </Feedback>}
      {resumeState && (profile.state === 'missing' || profile.state === 'ready') &&
        <ProfileForm key={`${userId}-${draft?.content_id ?? 'manual'}`} initial={draft ? mergeDraft(saved, draft.fields) : saved} save={saveProfile} />}
    </section>
  )
}
