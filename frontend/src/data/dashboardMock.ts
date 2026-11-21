import { routes } from '../routes'

export const modules = [
  { title: 'AI 职业画像', description: '梳理个人经历和能力，明确求职方向。', route: routes.career, tone: 'violet' },
  { title: '岗位智能匹配', description: '拆解岗位要求，识别匹配点和能力差距。', route: routes.jobs, tone: 'blue' },
  { title: 'AI 项目探索', description: '从兴趣和观察出发，寻找适合实践的项目。', route: routes.interests, tone: 'teal' },
  { title: '项目理解与面试', description: '理解项目架构与代码，准备面试表达。', route: routes.workspace, tone: 'amber' },
  { title: 'AI 成长导师', description: '规划学习路线，持续积累实践与成长记录。', route: routes.growth, tone: 'violet' },
]

export const skills = [
  { label: '产品思维', score: 64 },
  { label: 'Python', score: 45 },
  { label: 'SQL', score: 52 },
  { label: 'AI 技术理解', score: 58 },
  { label: '项目实践', score: 36 },
  { label: '面试表达', score: 42 },
]

export const tasks = [
  { id: 'career-profile', title: '完成个人职业画像' },
  { id: 'analyze-jd', title: '分析目标岗位 JD' },
  { id: 'first-project', title: '完成第一个 AI 产品项目' },
  { id: 'first-interview', title: '进行第一次模拟面试' },
] as const

export type TaskId = (typeof tasks)[number]['id']

export const growthSteps = ['职业定位', '项目探索', '项目实践', '简历优化', '面试准备']
