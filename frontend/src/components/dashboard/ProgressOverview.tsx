import { useId, type ReactNode } from 'react'
import { Link } from 'react-router'
import { routes } from '../../routes'
import { statuses } from '../../services/applications'
import type { Dashboard } from '../../services/dashboard'
import { Feedback } from '../common/Feedback'
import { states } from '../learning/LearningPanels'

const skillLabels = { verified: '测评已验证', self_reported: '用户自述', inferred: '推断或参考', unknown: '待验证' } as const
const gapLabels: Record<string, string> = {
  partial: '部分符合', unmet: '暂未满足', pending_not_provided: '证据待补充',
  pending_no_evidence: '条件待核实', pending_interview: '待面试核实',
}

export function OverviewPanel({ title, children, to, link }: {
  title: string; children: ReactNode; to?: string; link?: string
}) {
  const id = useId()
  return <section className="surface detail-panel progress-panel" aria-labelledby={id}>
    <div className="section-heading"><h2 id={id}>{title}</h2></div>
    <div className="progress-panel-body">{children}</div>
    {to && <Link className="button button-outline" to={to}>{link}</Link>}
  </section>
}

export function ProgressOverview({ data }: { data: Dashboard }) {
  const { skills, match, projects, tasks, interview, applications, next_action: next } = data
  const matchUrl = match ? `${routes.jobs.path}?job=${match.job_id}&match=${match.id}` : routes.jobs.path
  const interviewUrl = interview ? `${routes.interview.path}?tab=report&session=${interview.session_id}` : routes.interview.path
  const tasksUrl = routes.growth.path + '?tab=daily'
  const boardUrl = routes.applications.path + '?tab=board'
  const actionTarget = {
    application: `${boardUrl}&application=${next.application_id}`, learning: tasksUrl, interview: interviewUrl,
    matching: matchUrl, profile: routes.profile.path, exploration: routes.interests.path,
  }[next.kind]

  return <>
    <OverviewPanel title="下一步行动" to={actionTarget} link="前往处理">
      <p className="font-semibold">{next.text}</p>
      <p className="text-muted">{next.kind === 'application' ? '来自你在投递看板保存的行动' : '根据当前记录建议'}</p>
    </OverviewPanel>
    <div className="dashboard-details">
      <OverviewPanel title="我的能力画像" to={routes.growth.path + '?tab=diagnosis'} link="查看能力诊断">
        {skills.verified + skills.self_reported + skills.inferred === 0 &&
          <Feedback kind="empty">暂无能力证据，可先补充档案或参加测评。</Feedback>}
        <ul className="progress-list">
          {Object.entries(skillLabels).map(([key, label]) =>
            <li key={key}>{label} · {skills[key as keyof typeof skills]} 项</li>)}
        </ul>
      </OverviewPanel>
      <OverviewPanel title="当前能力差距" to={matchUrl} link="打开岗位匹配">
        {match ? <>
          <p className="font-semibold">{match.position}</p>
          {match.gaps.length ? <ul className="progress-list">{match.gaps.map((item, index) =>
            <li key={index}><span>{item.name}</span><span className="badge">{gapLabels[item.status] ?? '待核对'}</span></li>)}
          </ul> : <Feedback kind="empty">这份匹配报告暂无待核对项。</Feedback>}
        </> : <Feedback kind="empty">完成岗位匹配后，可在这里查看差距和待补充的证据。</Feedback>}
      </OverviewPanel>
      <OverviewPanel title="推荐项目" to={routes.projects.path} link="打开项目推荐">
        {projects.length ? <ul className="progress-list">{projects.map((item) => <li key={item.id}>
          <Link className="font-medium text-brand hover:underline" to={routes.projects.path + '?session=' + item.session_id}>{item.name}</Link>
          {item.selected && <span className="badge" data-tone="violet">已选项目</span>}
        </li>)}</ul> : <Feedback kind="empty">暂无项目推荐。可以从一条感兴趣的业务问题开始探索。</Feedback>}
      </OverviewPanel>
      <OverviewPanel title="今日学习任务" to={tasksUrl} link="打开每日任务">
        {tasks.length ? <ul className="progress-list">{tasks.map((item) => <li key={item.id}>
          <span>{item.title} <span className="text-muted">· {item.minutes} 分钟</span></span>
          <span className="badge">{states[item.status] ?? '待核对'}</span>
        </li>)}</ul> : <Feedback kind="empty">今日暂无已安排任务。可到成长中心查看学习路线和安排。</Feedback>}
      </OverviewPanel>
      <OverviewPanel title="最近模拟面试" to={interviewUrl} link={interview ? '查看面试报告' : '打开面试训练'}>
        {interview ? <>
          <p className="font-semibold">{interview.target}</p>
          <p>已作答 {interview.answered} 题 · {interview.score === null ? '证据不足，暂无评分' : `参考分 ${interview.score}`}</p>
          {interview.weakness && <p className="text-muted">可优先复盘：{interview.weakness}</p>}
        </> : <Feedback kind="empty">暂无已完成的模拟面试报告。</Feedback>}
      </OverviewPanel>
      <OverviewPanel title="当前投递进度" to={boardUrl} link="打开投递看板">
        {Object.keys(applications).length ? <ul className="progress-list">
          {Object.entries(statuses).filter(([key]) => applications[key as keyof typeof applications]).map(([key, label]) =>
            <li key={key}><span>{label}</span><strong>{applications[key as keyof typeof applications]} 条</strong></li>)}
        </ul> : <Feedback kind="empty">暂无投递记录。可在求职执行添加并跟进目标岗位。</Feedback>}
      </OverviewPanel>
    </div>
  </>
}
