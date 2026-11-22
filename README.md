# AI Career Copilot · AI 求职成长助手

面向希望进入 AI 产品、AI Agent 产品和 AI 应用行业的学生，帮助他们逐步建立职业定位、项目实践和面试表达能力。

当前版本覆盖账户与档案、简历和职业画像、岗位匹配、产品探索、项目学习、模拟面试、成长中心和投递管理。登录后的驾驶舱汇总当前账号的记录。

[产品作品集与演示入口](docs/stage11/PORTFOLIO.md) · [GitHub 项目说明](docs/stage11/README.md)

**核心场景**：用一份简历和一份目标 JD 找出最应该先补的证据。看完报告后，用户可修改一处真实经历，再使用同一份 JD 复查。项目、面试和投递记录保留所用资料的来源与版本。

![求职驾驶舱，真实前端与合成账号数据](docs/stage11/screenshots/dashboard.png)

[产品核心案例](docs/stage11/PROJECT_CASE_STUDY.md) · [系统与 AI 架构图](docs/stage11/SYSTEM_ARCHITECTURE.md) · [本地运行与数据库初始化](docs/stage11/README.md#本地运行)

## 第十阶段交付

- [系统审计与前九阶段完成度](docs/SYSTEM_AUDIT.md) 汇总初始问题、后续修复证据和当前试用门槛。[架构与工作流](docs/ARCHITECTURE.md) [跨模块数据衔接](docs/CROSS_MODULE_WORKFLOW.md)
- [端到端验收](docs/PRODUCT_ACCEPTANCE.md) 记录实际数据库、浏览器、权限和性能结果。最终隔离回归为 120 项通过，10 项外部服务用例按配置跳过。
- [统一模型调用和提示词评估](docs/AI_EVALUATION.md) 与 [性能、安全、Token 和成本](docs/PERFORMANCE_SECURITY.md) 记录 AI 质量基线、数据处理边界和复测方式。[Provider 源码](backend/app/ai/provider.py)
- [部署与恢复](docs/DEPLOYMENT.md) 提供本地、测试和生产运行方式。[Docker Compose](compose.yaml) [数据库迁移](docs/DATABASE.md)
- [五人用户试用](docs/USER_VALIDATION.md) 和 [商业化验证](docs/COMMERCIAL_VALIDATION.md) 可用于安排试用和收集行为证据。公网部署、实时外部服务复测及真人试用结果仍待验收。

## 本地启动

Windows 可运行 `scripts/start_desktop.ps1` 打开独立窗口。启动器会复用已有的本地服务，缺少时启动 MySQL、API 和前端。后台 AI 任务进程单独启动。

请在独立的 PowerShell 窗口运行各项命令。先等 MySQL 启动，再运行后端和任务进程。

```powershell
# 终端 1：本机专用 MySQL
python scripts/start_local_mysql.py

# 终端 2：FastAPI
& backend/.venv/Scripts/python.exe -m uvicorn --app-dir backend app.main:create_app --factory --host 127.0.0.1 --port 8001

# 终端 3：React
npm.cmd --prefix frontend run dev

# 终端 4：简历解析和 AI 任务进程
Set-Location backend
& .venv/Scripts/python.exe -m app.resume_worker --approved-host dashscope.aliyuncs.com
```

打开 [求职驾驶舱](http://127.0.0.1:5173/) 或 [FastAPI 接口文档](http://127.0.0.1:8001/docs)。API 使用 8001，以避开本机已使用的 8000。预览可匿名访问，个人档案需要登录。

运行 API 和 Worker 前执行 Alembic 迁移。可通过 [进程检查](http://127.0.0.1:8001/health) 和 [就绪检查](http://127.0.0.1:8001/ready) 定位本地故障。账户删除与文件清理流程见 [运行维护说明](docs/OPERATIONS.md)。

质量基线、提示词版本、失败案例和复测命令见 [AI 评估说明](docs/AI_EVALUATION.md)。

职业画像入口是 [AI 职业画像](http://127.0.0.1:5173/career-profile)，登录后使用。AI 调用需在本地配置 `LLM_BASE_URL`、`LLM_MODEL` 和 `LLM_API_KEY`。项目当前使用阿里云百炼的北京兼容端点与 `deepseek-v4.1-flash`。变更配置后重启 FastAPI 和任务进程。详见 [Provider 配置、流程与评测](docs/RESUME_AI.md)。

[岗位匹配](http://127.0.0.1:5173/job-matching) 支持 JD 导入、证据评分、历史报告和求职建议。岗位与简历共用同一个 Worker。评分规则和操作步骤见 [岗位匹配说明](docs/JOB_MATCHING.md)。

[求职执行工作台](http://127.0.0.1:5173/application-workspace) 支持岗位录入与收藏、简历版本、投递看板、日程、数据分析和 AI 策略。升级到数据库迁移 `20261121_0009` 后重启后端和共享 Worker。详细流程、统计口径和复测命令见 [第九阶段说明](docs/JOB_APPLICATIONS.md)。

新环境首次安装依赖：

```powershell
python -m venv backend/.venv
& backend/.venv/Scripts/python.exe -m pip install -r backend/requirements.txt
npm.cmd --prefix frontend ci
```

从 `backend/.env.example` 创建本地 `backend/.env`，填入数据库账户密码和独立生成的 JWT 密钥，再按 [数据库文档](docs/DATABASE.md) 初始化和执行迁移。本机使用 Python 3.14.8、Node.js 24.18.0。前端构建命令为 `npm.cmd --prefix frontend run build`。

Docker 本地、测试及生产配置见 [Docker 与生产部署](docs/DEPLOYMENT.md)，包含 HTTPS、数据库迁移、备份恢复和回滚。

## 从哪里开始读代码

[成长中心](http://127.0.0.1:5173/growth) 提供能力诊断、学习路线、每日任务、AI 带练、作业和测评。迁移后重启共享 Worker，详见[学习导师说明](docs/LEARNING.md)。

[AI 面试训练](http://127.0.0.1:5173/interview-practice) 提供五种文字模拟模式，复用当前任务进程。首次使用先执行迁移。流程、评分规则与复测命令见[第七阶段面试说明](docs/INTERVIEW.md)。

[项目工作台](http://127.0.0.1:5173/project-workspace) 复用当前的 Worker。首次使用前执行数据库迁移。仓库接入、代码证据和练习流程见[第六阶段使用与复测](docs/PROJECT_MENTOR.md)。

第五阶段从「兴趣探索」与「项目推荐」进入。使用同一 Worker 运行对话、研究、推荐和 PRD。联网搜索需在本地设置 `TAVILY_API_KEY`。也可补录已核对的公开资料。详见[产品探索使用与复测](docs/PRODUCT_DISCOVERY.md)。

1. `frontend/src/main.tsx` 将 React 应用挂载到 HTML，并启用浏览器路由。
2. `frontend/src/routes.ts` 声明路径、标题、图标、导航组和后续规划。共享布局使用同一份信息显示侧栏和面包屑。
3. [DashboardPage.tsx](frontend/src/pages/DashboardPage.tsx) 发起当前账号的查询并处理加载、失败和重试。
4. [dashboard_service.py](backend/app/services/dashboard_service.py) 按账户汇总职业诊断、学习、面试和投递记录。多个界面复用业务口径，调整首页统计时可查回实际业务记录。
5. [resume_worker.py](backend/app/resume_worker.py) 执行较慢的后台任务，更新持久化状态。应用查询任务状态后展示结果。在隔离环境停掉 Worker，可观察 API 继续响应而就绪检查报告任务进程失联的情况。

注册和登录从 `backend/app/api/v1/endpoints/auth.py` 开始阅读，档案的权限依赖在 `backend/app/api/dependencies.py`。浏览器的登录状态由 `frontend/src/hooks/AuthProvider.tsx` 管理。

项目资料包括 [PRD](docs/PRD.md)、[技术架构](docs/ARCHITECTURE.md)、[API 文档](docs/API.md)、[数据库设计](docs/DATABASE.md)、[测试计划](docs/TEST_PLAN.md) 和 [更新记录](docs/CHANGELOG.md)。
