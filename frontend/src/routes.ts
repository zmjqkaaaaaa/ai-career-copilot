import {
  AudioLines, Compass, FolderKanban, LayoutDashboard, Lightbulb,
  ScanFace, Settings, Sprout, Target, UserRound,
} from 'lucide-react'
import type { LucideIcon } from 'lucide-react'

type RouteInfo = {
  path: string
  title: string
  group: string
  icon: LucideIcon
  description: string
  planned: string[]
}

export const routes = {
  dashboard: { path: '/', title: '求职驾驶舱', group: '工作台', icon: LayoutDashboard, description: '查看求职进展和近期任务。', planned: [] },
  career: { path: '/career-profile', title: 'AI 职业画像', group: '职业定位', icon: ScanFace, description: '梳理已有经历、能力证据和目标方向，建立可编辑的职业画像。', planned: ['上传 PDF 或 DOCX 简历', '提取经历与技能证据', '确认并编辑职业画像'] },
  jobs: { path: '/job-matching', title: '岗位匹配', group: '职业定位', icon: Target, description: '对照目标岗位的要求，识别匹配点和需要补足的能力。', planned: ['录入目标岗位 JD', '拆解岗位要求', '展示匹配依据和能力差距'] },
  applications: { path: '/application-workspace', title: '求职执行', group: '工作台', icon: FolderKanban, description: '管理岗位、投递和面试日程。', planned: [] },
  interests: { path: '/interest-exploration', title: '兴趣探索', group: '项目探索', icon: Compass, description: '从兴趣、亲身经历和观察到的问题出发，找到值得探索的方向。', planned: ['记录兴趣和经历', '收集业务场景中的问题', '整理待验证的机会'] },
  projects: { path: '/project-recommendations', title: '项目推荐', group: '项目探索', icon: Lightbulb, description: '根据目标岗位与当前基础，选择可实践的 AI 产品项目。', planned: ['生成项目候选方向', '说明项目范围与前置能力', '整理可实践的 MVP 计划'] },
  workspace: { path: '/project-workspace', title: '项目工作台', group: '项目实践', icon: FolderKanban, description: '记录项目进展，理解架构和关键代码，整理可复述的项目经验。', planned: ['接入经授权的公开 GitHub 仓库', '梳理文件结构和核心流程', '按知识点完成代码理解练习'] },
  interview: { path: '/interview-practice', title: 'AI 面试训练', group: '项目实践', icon: AudioLines, description: '围绕目标岗位和项目经历练习面试，记录回答与反馈。', planned: ['选择面试主题', '逐题记录作答', '查看反馈和改进建议'] },
  growth: { path: '/growth', title: '成长中心', group: '个人成长', icon: Sprout, description: '根据目标岗位与实践进度安排学习任务，记录能力成长。', planned: ['建立学习路线', '管理实践任务', '记录学习进展'] },
  profile: { path: '/profile', title: '个人档案', group: '个人成长', icon: UserRound, description: '管理教育背景、求职目标和经历。', planned: [] },
  settings: { path: '/settings', title: '设置', group: '账户', icon: Settings, description: '管理账户偏好、通知和数据设置。', planned: ['管理账户偏好', '配置通知方式', '查看数据管理选项'] },
  login: { path: '/login', title: '登录', group: '账户', icon: UserRound, description: '登录账户。', planned: [] },
  register: { path: '/register', title: '注册账户', group: '账户', icon: UserRound, description: '创建账户。', planned: [] },
} satisfies Record<string, RouteInfo>

export const routeList = Object.values(routes)
export const placeholderRoutes = [
  routes.settings,
]
export const navigationGroups = [
  { title: '工作台', items: [routes.dashboard, routes.applications] },
  { title: '职业定位', items: [routes.career, routes.jobs] },
  { title: '项目探索', items: [routes.interests, routes.projects] },
  { title: '项目实践', items: [routes.workspace, routes.interview] },
  { title: '个人成长', items: [routes.growth, routes.profile] },
]

export type AppRoute = (typeof routeList)[number]
