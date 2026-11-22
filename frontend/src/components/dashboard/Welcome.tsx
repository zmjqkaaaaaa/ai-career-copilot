import { Orbit, Sparkles } from 'lucide-react'
import { Link } from 'react-router'
import { useAuth } from '../../hooks/AuthProvider'
import { routes } from '../../routes'
import type { Dashboard } from '../../services/dashboard'

export function Welcome({ data, failed }: { data?: Dashboard; failed?: boolean }) {
  const { account } = useAuth()
  return (
    <section className="hero" aria-labelledby="welcome-title">
      <div className="hero-content">
        <h1 id="welcome-title">{account ? `你好，${account.username}` : '你好，欢迎使用'}<br />AI Career Copilot</h1>
        <p>{account ? '查看你的求职进展，继续推进下一步。' : '从认识自己开始，逐步建立 AI 产品经理求职竞争力。'}</p>
        <div className="hero-actions">
          <Link className="button button-primary" to={account ? routes.profile.path : routes.login.path}>
            <Sparkles size={18} aria-hidden="true" /> {account ? '编辑个人档案' : '登录查看我的进展'}
          </Link>
          {account && <span className="hero-target"><span>当前目标岗位</span><strong>
            {data ? data.target_position ?? '未设置' : failed ? '读取失败' : '读取中'}
          </strong></span>}
          {data && <span className="hero-target">个人档案 · {data.profile_complete ? '已创建' : '待填写'}</span>}
        </div>
      </div>
      <div className="hero-decoration" aria-hidden="true">
        <div className="hero-orbit hero-orbit-outer" />
        <div className="hero-orbit hero-orbit-inner" />
        <div className="hero-emblem"><Orbit size={69} strokeWidth={1.35} /></div>
        <Sparkles className="hero-sparkle" size={29} strokeWidth={1.5} />
      </div>
    </section>
  )
}
