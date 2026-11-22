# AI Career Copilot 技术决策

阶段 11.4 · 2026 年 11 月 22 日

本记录按现有实现解释设计取舍。“为什么”是基于代码和产品约束的解释。团队当时未记录的选型讨论或独立贡献归属，保留为待确认。

## 1. 主要技术选型

| 选型 | 作用与适配理由 | 优势 | 局限与替代 | 实际位置 |
| --- | --- | --- | --- | --- |
| React | 通过组件和状态驱动界面，适合长任务预览、轮询、空态和历史切换 | 跨模块复用导航、表单及反馈，视图按 URL 直接进入 | 多页面状态共享需明确边界。替代 Vue；如需服务端渲染再评估 Next.js | [App.tsx](../../frontend/src/App.tsx)、[CareerProfilePage](../../frontend/src/pages/CareerProfilePage.tsx) |
| TypeScript | 在浏览器代码中检查表单、任务、版本及响应字段 | 帮助定位错误字段或分支，重构导航和跨模块跳转更容易 | 静态类型不能验证服务端实际响应。替代原生 JS 加 JSDoc，或进一步引入运行时 API 契约 | [services/jobs.ts](../../frontend/src/services/jobs.ts)、[services/api.ts](../../frontend/src/services/api.ts) |
| Vite 与 Tailwind CSS | 负责开发代理、构建静态资源和通用样式 | 本地同源调试，浏览器构建和样式配置集中 | Vite 代理只服务开发，生产另由 Caddy；样式跨页一致性仍需组件约束。替代 webpack/Rspack 与 CSS Modules | [vite.config](../../frontend/vite.config.ts)、[package.json](../../frontend/package.json) |
| Python | 实现规则、文档解析、任务处理和 AI 服务接入 | 数据和 AI 生态丰富，业务规则可用纯函数和测试核对 | 重 CPU 或大量并发时要衡量进程与资源。替代 TypeScript 后端搭配 Python 专项任务 | [resume_parser](../../backend/app/services/resume_parser.py)、[job_matching_service](../../backend/app/services/job_matching_service.py) |
| FastAPI | 通过 Router、依赖注入和响应模型组织 API | 统一鉴权和输入验证，路由可由 OpenAPI 查看 | 服务层边界需要项目维护，长任务需单独执行。替代 Django REST Framework 或 Flask | [main.py](../../backend/app/main.py)、[API Router](../../backend/app/api/v1/api.py) |
| MySQL 8.4 | 事务保存归属、业务数据、版本、队列及事件 | 同一事务可保存报告与关联状态，复合索引和行锁支持并发场景 | 队列、长表和数据库迁移会占用运维资源。替代 PostgreSQL；SQLite 可作轻量原型，需重新验证并发与迁移语义 | [compose.yaml](../../compose.yaml)、[数据库设计](DATABASE_DESIGN.md) |
| SQLAlchemy 2 与 Alembic | SQLAlchemy 管理 ORM、Session 和查询。Alembic 管理版本迁移 | 显式声明主键、外键及事务，模型与表结构可共同检查 | 需理解生成的 SQL、索引和会话边界。替代显式 SQL 与独立迁移工具 | [session.py](../../backend/app/db/session.py)、[models](../../backend/app/models)、[迁移](../../backend/alembic/versions) |
| Pydantic | 校验 API 数据及模型 JSON，生成 JSON Schema | 格式和类型失败能明确处理，输出字段稳定 | 需要额外核对引文、事实和业务一致性。替代 JSON Schema 验证器加手工 DTO | [schemas](../../backend/app/schemas)、[Provider](../../backend/app/ai/provider.py) |
| JWT 与 Argon2 | JWT 用于签名后的身份声明；口令用 Argon2 带盐哈希 | 可分别限制浏览器与 API audience；浏览器 Cookie 为 HttpOnly；数据库只保留口令哈希 | 有效期内的 Token 需要保护；撤销设计及轮换成为扩展点。替代服务端会话 ID、集中 OIDC，口令哈希可选其他经评估方案 | [security.py](../../backend/app/core/security.py)、[auth_service.py](../../backend/app/services/auth_service.py)、[auth.py](../../backend/app/api/v1/endpoints/auth.py) |
| 兼容 Chat Completions 的模型 | 补充抽取、讲解、追问和文本建议；历史基线使用百炼 `deepseek-v4.1-flash` | Provider 集中管理模型、地址、最大输出、超时和校验，可用固定响应回归 | 供应商的格式支持、延迟、成本和质量需单独测试；可替换兼容模型或自托管模型并复测 | [Provider](../../backend/app/ai/provider.py)、[配置](../../backend/app/core/config.py)、[历史基线](../AI_EVALUATION.md) |
| GitHub REST API | 读取公开仓库及指定提交对应的文件 | SHA 与行号让解释可复核，可按文件和范围截取 | 有配额、文件类型及访问边界；替代用户提供合规的只读代码附件，或受控上传源码包 | [github_service.py](../../backend/app/services/github_service.py)、[code_project_workflow.py](../../backend/app/services/code_project_workflow.py) |
| Tavily | 在用户确认后搜索公开关键词，并与手工资料进入同一研究流程 | 降低手工收集成本，返回来源标识和摘录 | 来源可信度、时效、服务配置与配额仍需核对；替代官方资料手工录入或其他可审核搜索服务 | [market_research_service.py](../../backend/app/services/market_research_service.py)、[discovery_workflow.py](../../backend/app/services/discovery_workflow.py) |
| Caddy 与 Docker Compose | 在同源下提供前端静态页面和 API 代理，统一服务与持久化卷 | 本地或单机部署可复用镜像，迁移和 Worker 独立，支持准备 HTTPS 的配置 | 仍需生产验证、监控及备份恢复。部署规模扩大后可评估托管服务 | [Caddyfile](../../frontend/Caddyfile)、[compose.yaml](../../compose.yaml)、[生产覆写](../../compose.production.yaml) |

## 2. 对产品影响较大的架构决策

| 决策 | 选择与理由 | 重新评估的条件 |
| --- | --- | --- |
| 用 Python 固定流程和状态 | 模型负责理解材料和生成草稿。权限、版本、完成条件与下一步由业务代码决定，便于重放和验证。 | 若出现无法预先描述的有效多步骤需求，先做可量化的对照试验，再决定是否引入 Agent。 |
| 共享 Worker 与数据库队列 | 同一数据库保存任务、指纹、状态和输出。用户可立即取到任务编号，长耗时步骤异步运行。 | 并发积压、数据库争用或不同队列独立扩容成为可复现问题时，比较 Redis/Celery 等独立队列。 |
| 报告关联输入版本 | JD 修订、简历内容和 Git 提交纳入证据。便于复查旧结果及解释差距变化。 | 存储增长明显时按资料生命周期和复查频次设计归档，同时检验证据链接是否保留。 |
| 测试模型输出用双重校验 | Pydantic 负责形状，领域服务验证原文引用、评分、版本与状态；失败回写任务。 | 模型换版本或提示词变化时，使用同一合成用例和人工复核，区分结构通过与业务通过。 |
| 前端 Cookie 同源访问 | HttpOnly 降低脚本直接读取令牌的机会，写操作加入来源和自定义请求头校验。 | 多客户端或跨域 BFF 部署前，重新评估会话恢复、登出撤销、密钥轮换和 CSRF 策略。 |
| 文件卷与数据库分别管理 | 私有文件持久化为独立卷，数据库保存文件引用和待删除任务。备份需成对。 | 多实例共享、跨区备份或大量文件访问出现时，再评估私有对象存储和迁移成本。 |

验收范围见 [系统架构](SYSTEM_ARCHITECTURE.md) 和 [发布与恢复](../DEPLOYMENT.md)。部署文件、历史合成评估和实际生产环境属于各自独立的证据。
