import { useEffect, useState } from 'react'
import { Link } from 'react-router'
import { skills } from '../../data/dashboardMock'
import { useAuth } from '../../hooks/AuthProvider'
import { routes } from '../../routes'
import { learning, type Diagnosis } from '../../services/learning'

export function SkillProfile() {
  const { account } = useAuth()
  const userId = account?.id
  const [result, setResult] = useState<{ userId: number; data: Diagnosis | null } | null>(null)
  useEffect(() => {
    if (!userId) return
    let ignore = false
    learning.diagnosis().then((data) => { if (!ignore) setResult({ userId, data }) })
      .catch(() => { if (!ignore) setResult({ userId, data: null }) })
    return () => { ignore = true }
  }, [userId])
  if (userId) {
    const snapshot = result?.userId === userId ? result : null
    const summary = snapshot?.data?.summary
    const labels = { verified: '测评已验证', self_reported: '用户自述', inferred: '推断或参考', unknown: '待验证' }
    return <section className="surface detail-panel" aria-labelledby="skills-title">
      <div className="section-heading"><h2 id="skills-title">我的能力画像</h2></div>
      {!snapshot && <p role="status">正在读取能力证据…</p>}
      {snapshot && !snapshot.data && <p>能力证据暂时读取失败。</p>}
      {summary && <ul className="grid gap-2">
        {Object.entries(labels).map(([key, label]) => <li key={key}>{label} · {summary[key]} 项</li>)}
      </ul>}
      <Link className="button button-outline mt-3" to={routes.growth.path + '?tab=diagnosis'}>查看能力诊断</Link>
    </section>
  }
  return (
    <section className="surface detail-panel" aria-labelledby="skills-title">
      <div className="section-heading">
        <h2 id="skills-title">我的能力画像</h2>
        <span className="badge" data-tone="violet">演示数据</span>
      </div>
      <p className="panel-description">登录后可以查看自己的能力证据。</p>
      <ul className="skill-list">
        {skills.map(({ label, score }) => (
          <li key={label}>
            <span>{label}</span>
            <div className="skill-track" aria-hidden="true"><div style={{ width: `${score}%` }} /></div>
            <span className="skill-score"><span className="sr-only">演示分数</span>{score}<span className="sr-only">分，满分 100</span></span>
          </li>
        ))}
      </ul>
    </section>
  )
}
