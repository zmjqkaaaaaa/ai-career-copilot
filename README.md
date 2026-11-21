# AI Career Copilot · AI 求职成长助手

面向希望进入 AI 产品、AI Agent 产品和 AI 应用行业的学生，帮助他们逐步建立职业定位、项目实践和面试表达能力。

当前版本覆盖注册、登录、个人档案、AI 职业画像、岗位匹配、产品探索和项目工作台。工作台可导入公开 GitHub 仓库，阅读固定提交版本的代码并完成理解测试。

## 本地启动

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

## 从哪里开始读代码

[成长中心](http://127.0.0.1:5173/growth) 提供能力诊断、学习路线、每日任务、AI 带练、作业和测评。迁移后重启共享 Worker，详见[学习导师说明](docs/LEARNING.md)。

[AI 面试训练](http://127.0.0.1:5173/interview-practice) 提供五种文字模拟模式，复用当前任务进程。首次使用先执行迁移。流程、评分规则与复测命令见[第七阶段面试说明](docs/INTERVIEW.md)。

[项目工作台](http://127.0.0.1:5173/project-workspace) 复用当前的 Worker。首次使用前执行数据库迁移。仓库接入、代码证据和练习流程见[第六阶段使用与复测](docs/PROJECT_MENTOR.md)。

第五阶段从「兴趣探索」与「项目推荐」进入。使用同一 Worker 运行对话、研究、推荐和 PRD。联网搜索需在本地设置 `TAVILY_API_KEY`。也可补录已核对的公开资料。详见[产品探索使用与复测](docs/PRODUCT_DISCOVERY.md)。

1. `frontend/src/main.tsx` 将 React 应用挂载到 HTML，并启用浏览器路由。
2. `frontend/src/routes.ts` 声明路径、标题、图标、导航组和后续规划。共享布局使用同一份信息显示侧栏和面包屑。
3. `frontend/src/pages/DashboardPage.tsx` 组合驾驶舱的六个区域。各个组件可以单独阅读和修改。
4. `frontend/src/data/dashboardMock.ts` 存放前端演示数据。尝试改一项演示分数，观察能力图的数字和条长一起变化。
5. `frontend/src/hooks/useDemoTasks.ts` 保存演示任务的完成状态。任务 ID 在 TypeScript 中由示例列表推导，拼错 ID 会在类型检查时暴露。

注册和登录从 `backend/app/api/v1/endpoints/auth.py` 开始阅读，档案的权限依赖在 `backend/app/api/dependencies.py`。浏览器的登录状态由 `frontend/src/hooks/AuthProvider.tsx` 管理。

项目资料包括 [PRD](docs/PRD.md)、[技术架构](docs/ARCHITECTURE.md)、[API 文档](docs/API.md)、[数据库设计](docs/DATABASE.md)、[测试计划](docs/TEST_PLAN.md) 和 [更新记录](docs/CHANGELOG.md)。
