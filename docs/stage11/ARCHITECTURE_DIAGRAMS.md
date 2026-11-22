# AI Career Copilot 架构图与业务时序

阶段 11.4 · 2026 年 11 月 22 日

[系统总体架构](SYSTEM_ARCHITECTURE.md) · [AI 技术架构](AI_WORKFLOW.md) · [数据库 ER 图](DATABASE_DESIGN.md)

图中 API 路径省略 `/api/v1`，{} 表示路径参数。API 与 Service 都运行在 FastAPI 进程；后台 Worker 是另一进程，使用相同数据模型。

图表使用 GitHub Markdown 的 `mermaid` 代码块。阶段验收在本地 Mermaid 11.12.0 中进行。GitHub 页面采用其部署的渲染版本。 [GitHub 图表文档](https://docs.github.com/en/get-started/writing-on-github/working-with-advanced-formatting/creating-diagrams)

## 1. 用户注册与登录

```mermaid
sequenceDiagram
  actor U as 用户
  participant F as AuthPage / auth.ts
  participant A as auth.py / dependencies.py
  participant S as auth_service.py / security.py
  participant D as MySQL users
  U->>F: 填写注册资料
  F->>A: POST /auth/register
  A->>S: register 校验并生成 Argon2 哈希
  S->>D: 写入 User，邮箱唯一
  D-->>S: 持久化或冲突
  alt 注册成功
    A-->>F: 201 UserRead
    F-->>U: 跳转登录并带入邮箱
    F->>A: POST /auth/session 表单
    A->>S: 校验 Origin 和限流后 authenticate
    S->>D: 查询 User 并核对密码摘要
    alt 认证通过
      S-->>A: issue_token 签发 browser audience 的 JWT
      A-->>F: UserRead 与 HttpOnly Cookie
      F->>A: GET /users/me，携带 Cookie
      A->>D: current_user 验证后读取账号
      A-->>F: 恢复受保护页面或驾驶舱
    else 认证失败
      A-->>F: 认证问题或限流提示
    end
  else 注册冲突
    A-->>F: 返回可读错误
  end
```

依据 [账户页](../../frontend/src/pages/AuthPage.tsx)、[认证路由](../../backend/app/api/v1/endpoints/auth.py)、[认证服务](../../backend/app/services/auth_service.py)、[当前用户依赖](../../backend/app/api/dependencies.py) 和 [用户模型](../../backend/app/models/user.py)。

## 2. 简历上传与 AI 解析

```mermaid
sequenceDiagram
  actor U as 用户
  participant F as CareerProfilePage / career.ts
  participant A as resumes.py / career.py
  participant D as MySQL / 私有简历目录
  participant W as resume_worker.py
  participant M as Provider 和模型
  U->>F: 选择 PDF 或 DOCX
  F->>A: POST /resumes/upload
  A->>D: create_resume 私有原件及 Resume 元数据
  F->>A: POST /resumes/{id}/parse
  A->>D: start_job 创建 ResumeJob
  W->>D: claim_job 读取文件，完成本地解析
  W->>D: complete 写 ResumeContent 文本版本
  F->>A: GET /resume-jobs/{taskId} 和 GET /resumes/{id}/preview
  A-->>F: 任务状态与可核对的脱敏块
  U->>F: 隐藏敏感块并确认发送
  F->>A: POST /resumes/{id}/extract
  A->>D: 记录用户确认的输入和任务指纹
  W->>M: compute 使用 EXTRACT
  M-->>W: JSON 草稿或调用错误
  W->>D: 校验结构和证据，保存版本或失败原因
  F->>A: PUT /resumes/{id}/content，修订并确认结构化版本
  opt 申请职业画像
    F->>A: POST /career/analyze，确认当前材料和方向
    W->>M: ANALYZE
    W->>D: 写 CareerAnalysis、SkillProfile 与 SkillEvidence
    F->>A: GET /career/profile 读取报告
  end
```

依据 [简历路由](../../backend/app/api/v1/endpoints/resumes.py)、[职业画像路由](../../backend/app/api/v1/endpoints/career.py)、[任务入队](../../backend/app/services/resume_jobs.py)、[Worker](../../backend/app/resume_worker.py) 和 [简历模型](../../backend/app/models/resume.py)。失败可见任务原因，用户可调整后按对应操作重试。

## 3. 岗位 JD 智能匹配

```mermaid
sequenceDiagram
  actor U as 用户
  participant F as JobMatchingPage / jobs.ts
  participant A as jobs.py
  participant S as job_workflow / job_matching_service
  participant D as MySQL
  participant W as 后台 Worker
  participant M as Provider 和模型
  U->>F: 录入 JD
  F->>A: POST /jobs 和 GET /jobs/{id}/parse-preview
  U->>F: 确认解析的输入
  F->>A: POST /jobs/{id}/parse
  A->>S: enqueue 核对版本和模型服务
  S->>D: 写 JobAnalysisTask
  W->>M: run_job_once 调 parse_jd
  W->>D: 核对原句，保存结果或失败
  F->>A: GET /job-analysis-tasks/{id}
  F->>A: PUT /jobs/{id}/requirements，用户确认要求
  A->>D: write_requirements 保存要求修订
  F->>A: POST /jobs/{id}/match，指定简历版本
  A->>S: candidate / score / enrich
  S->>D: 读取确认要求和简历证据
  A->>D: 保存 JobMatch 和 JobSkillGap
  A-->>F: 匹配分、覆盖率、差距和证据
  opt 单独确认生成求职建议
    F->>A: POST /job-matches/{id}/recommendations
    W->>M: ADVICE_PROMPT
    W->>D: 将建议附于匹配报告或记录失败
  end
```

依据 [岗位路由](../../backend/app/api/v1/endpoints/jobs.py)、[JD 任务](../../backend/app/services/job_workflow.py)、[规则评分](../../backend/app/services/job_matching_service.py) 及 [岗位模型](../../backend/app/models/job.py)。版本冲突时重新读取材料，建议失败仍可查看规则报告。

## 4. GitHub 项目导入与代码理解

```mermaid
sequenceDiagram
  actor U as 用户
  participant F as ProjectWorkspacePage / codeProjects.ts
  participant A as code_projects.py
  participant D as MySQL 快照 / 文件 / 任务
  participant W as code_project_workflow.py
  participant G as GitHub REST API
  participant M as Provider 和模型
  U->>F: 输入公开 GitHub 仓库
  F->>A: POST /code-projects/import
  A->>D: import_repository 保存仓库和导入任务
  W->>G: collect_repository 读取元数据、提交和文件
  alt GitHub 返回可读内容
    W->>D: 固定 SHA，写 ProjectSnapshot 和 ProjectFile
    F->>A: GET /code-projects/{id}/files?commit=SHA
    F->>A: POST /code-projects/{id}/preview
    A->>D: 读取对应提交的可引用片段
    U->>F: 核对后同意发送代码片段
    F->>A: POST /code-projects/{id}/explain
    A->>D: enqueue_study 记录任务
    W->>M: model_result 请求讲解
    W->>D: 校验路径、引用和提交，存 ProjectLesson 或失败
    F->>A: GET /code-projects/{id}/explanations?commit=SHA
  else 限流或仓库不可读
    W->>D: 任务标记失败
    F-->>U: 显示原因，可更换仓库或稍后重试
  end
```

依据 [项目路由](../../backend/app/api/v1/endpoints/code_projects.py)、[项目工作流](../../backend/app/services/code_project_workflow.py)、[代码选材](../../backend/app/services/project_knowledge_service.py)、[GitHub 服务](../../backend/app/services/github_service.py) 和 [项目模型](../../backend/app/models/code_project.py)。

## 5. AI 模拟面试

```mermaid
sequenceDiagram
  actor U as 用户
  participant F as InterviewPracticePage / interview.ts
  participant A as interviews.py
  participant D as MySQL 面试数据
  participant W as interview_engine.py
  participant M as Provider 和模型
  F->>A: POST /interviews/prepare
  A->>D: 核对 JD、简历、投递或代码来源
  U->>F: 阅读快照及训练规则
  F->>A: POST /interviews/sessions
  A->>D: 保存 InterviewSession
  F->>A: POST /interviews/sessions/{id}/preview
  F->>A: POST /interviews/sessions/{id}/start
  A->>D: 校验确认票据后排队 InterviewTask
  W->>M: run_interview_once 生成开场题
  W->>D: 保存 Question 或失败状态
  loop 用户确认后提交作答，直至结束
    F->>A: POST 会话 /preview 后 POST /answers
    A->>D: 校验当前题和回合后入队
    W->>M: 评价及拟议追问
    W->>D: complete 校验证据并更新轮次或记录失败
    F->>A: GET /interviews/sessions/{id}
    A-->>F: 下题、评估状态或重试信息
  end
  F->>A: POST 会话 /finish 或 GET 会话 /report
  A->>D: finish 按已评范围保存或返回报告和复练任务
```

依据 [面试路由](../../backend/app/api/v1/endpoints/interviews.py)、[面试引擎](../../backend/app/services/interview_engine.py)、[结束与评分汇总](../../backend/app/services/interview_report_service.py) 和 [面试模型](../../backend/app/models/interview.py)。引擎也可在最后一轮自动完成，提前结束仍展示覆盖范围。

## 6. AI 学习任务与能力画像更新

```mermaid
sequenceDiagram
  actor U as 用户
  participant F as GrowthCenterPage / learning.ts
  participant A as learning.py / dashboard.py
  participant S as learning_plan / learning_workflow
  participant D as MySQL
  participant W as 学习 Worker
  participant M as Provider 和模型
  U->>F: 选方向、时间预算和可选报告
  F->>A: POST /learning/paths/generate
  A->>S: diagnosis 与 make_path
  S->>D: 按证据和先修写 LearningPath
  F->>A: GET /learning/tasks/daily
  A->>S: daily 核对先修、当日任务和本周预算
  S->>D: 读取或补建 LearningTask
  opt 用户选择导师答疑
    F->>A: POST /learning/sessions
    F->>A: POST /learning/preview，用户核对
    F->>A: POST /learning/sessions/{id}/messages
    A->>S: enqueue 绑定上下文和确认
    S->>D: 写 LearningJob
    W->>M: run_learning_once 调教学 Prompt
    W->>D: 保存 LearningMessage 或任务失败
  end
  F->>A: POST /learning/assessments/start
  F->>A: POST /learning/assessments/{id}/submit
  A->>D: 题库确定性判分，满足条件后更新掌握历史和路线
  F->>A: GET /learning/progress 或 GET /dashboard
  A-->>F: 返回能力证据状态和学习进展
```

依据 [学习 API](../../backend/app/api/v1/endpoints/learning.py)、[学习规则](../../backend/app/services/learning_plan.py)、[学习任务](../../backend/app/services/learning_workflow.py)、[学习模型](../../backend/app/models/learning.py) 和 [驾驶舱聚合](../../backend/app/services/dashboard_service.py)。这里更新的是学习能力诊断和驾驶舱聚合。阶段测评保留历史，并与原简历职业画像的证据记录分别维护。
