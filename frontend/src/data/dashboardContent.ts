import { routes } from '../routes'

export const modules = [
  { title: 'AI 职业画像', description: '梳理个人经历和能力，明确求职方向。', route: routes.career, tone: 'violet' },
  { title: '岗位智能匹配', description: '拆解岗位要求，识别匹配点和能力差距。', route: routes.jobs, tone: 'blue' },
  { title: 'AI 项目探索', description: '从兴趣和观察出发，寻找适合实践的项目。', route: routes.interests, tone: 'teal' },
  { title: '项目理解与面试', description: '理解项目架构与代码，准备面试表达。', route: routes.workspace, tone: 'amber' },
  { title: 'AI 成长导师', description: '规划学习路线，持续积累实践与成长记录。', route: routes.growth, tone: 'violet' },
]

export const growthSteps = ['职业定位', '项目探索', '项目实践', '简历优化', '面试准备']
