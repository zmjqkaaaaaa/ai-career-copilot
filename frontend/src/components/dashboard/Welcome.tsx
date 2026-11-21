import { Orbit, Sparkles } from 'lucide-react'
import { Link } from 'react-router'
import { useAuth } from '../../hooks/AuthProvider'
import { routes } from '../../routes'

export function Welcome() {
  const { account, checking, profile } = useAuth()
  const target = profile.state === 'ready' ? profile.data.target_position || '未设置'
    : checking || (account && profile.state === 'loading') ? '读取中'
    : profile.state === 'error' ? '读取失败' : account ? '未设置' : '登录后查看'
  return (
    <section className="hero" aria-labelledby="welcome-title">
      <div className="hero-content">
        <h1 id="welcome-title">{account ? `你好，${account.username}` : '你好，欢迎使用'}<br />AI Career Copilot</h1>
        <p>从认识自己开始，逐步建立 AI 产品经理求职竞争力。</p>
        <div className="hero-actions">
          <Link className="button button-primary" to={routes.career.path}>
            <Sparkles size={18} aria-hidden="true" /> 开始我的职业分析
          </Link>
          <span className="hero-target"><span>当前目标岗位</span><strong>{target}</strong></span>
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
