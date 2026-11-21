import { BriefcaseBusiness, ClipboardList, FileUser, Flag } from 'lucide-react'
import { useAuth } from '../../hooks/AuthProvider'

export function Overview() {
  const { account, checking, profile } = useAuth()
  let target = '登录后查看'
  let status = '登录后查看'
  if (checking || (account && profile.state === 'loading')) {
    target = status = '读取中'
  } else if (account) {
    if (profile.state === 'ready') {
      target = profile.data.target_position || '未设置'
      status = '已建立'
    } else if (profile.state === 'missing') {
      target = '未设置'
      status = '待建立'
    } else if (profile.state === 'error') {
      target = status = '读取失败'
    }
  }
  const overview = [
    { label: '当前目标岗位', value: target, icon: BriefcaseBusiness, tone: 'blue', demo: false },
    { label: '当前求职阶段', value: '职业定位', icon: Flag, tone: 'violet', demo: true },
    { label: '已完成项目数', value: '0 个', icon: ClipboardList, tone: 'teal', demo: true },
    { label: '个人档案状态', value: status, icon: FileUser, tone: 'amber', demo: false },
  ]
  return (
    <section aria-labelledby="overview-title">
      <div className="section-heading">
        <h2 id="overview-title">个人求职概览</h2>
      </div>
      <dl className="overview-grid">
        {overview.map(({ label, value, icon: Icon, tone, demo }) => (
          <div className="surface overview-card" key={label}>
            <span className="icon-tile" data-tone={tone}><Icon size={20} aria-hidden="true" /></span>
            <div className="min-w-0"><dt>{label} {demo && <span className="badge">示例</span>}</dt><dd className="wrap-anywhere">{value}</dd></div>
          </div>
        ))}
      </dl>
    </section>
  )
}
