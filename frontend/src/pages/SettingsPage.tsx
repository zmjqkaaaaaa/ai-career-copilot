import { useState, type FormEvent } from 'react'
import { useAuth } from '../hooks/AuthProvider'
import { errorMessage } from '../services/api'

export function SettingsPage() {
  const { deleteAccount } = useAuth()
  const [confirming, setConfirming] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const data = new FormData(event.currentTarget)
    setBusy(true)
    setError('')
    try {
      await deleteAccount(String(data.get('password') ?? ''))
    } catch (failure) {
      setError(errorMessage(failure))
    } finally {
      setBusy(false)
    }
  }

  return <section className="surface detail-panel">
    <h1>账户设置</h1>
    <h2>删除账户和个人数据</h2>
    <p>此操作会删除个人档案、简历及其版本、投递、面试和学习记录，并安排清理已上传的简历文件。删除无法撤销。</p>
    <p>第三方服务已接收的数据依照该服务的保留政策处理。</p>
    {confirming ? <form className="account-form" onSubmit={submit}>
      <label>当前密码<input name="password" type="password" autoComplete="current-password" required maxLength={128} /></label>
      <label className="application-check"><input type="checkbox" required />我确认永久删除此账户和相关数据</label>
      {error && <p role="alert" className="form-error">{error}</p>}
      <div className="flex flex-wrap gap-2">
        <button className="button button-filled" disabled={busy}>{busy ? '正在提交…' : '确认删除账户'}</button>
        <button className="button button-outline" type="button" disabled={busy} onClick={() => { setConfirming(false); setError('') }}>取消</button>
      </div>
    </form> : <div><button className="button button-outline" onClick={() => setConfirming(true)}>删除我的账户</button></div>}
  </section>
}
