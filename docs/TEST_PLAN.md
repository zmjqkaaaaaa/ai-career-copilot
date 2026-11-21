# 测试计划

## 前八阶段跨模块验收

自动化回归 93 项通过、8 项跳过，其中同账号贯通用例和原有浏览器回归均通过。另运行同账号真实 GitHub 导入变体及四项真实百炼用例，共 5 项通过。独立启用真实百炼的简历与岗位浏览器用例另有 2 项通过。数据库迁移和前端构建通过。Tavily 密钥未配置，市场研究使用补录资料验证。运行范围、身份隔离和记录证据见[产品验收矩阵](PRODUCT_ACCEPTANCE.md)。

## 第八阶段验证

开发库与测试库迁移到 `20261121_0007`，Alembic 一致性和前端生产构建通过。启用成长中心、面试、项目和产品探索浏览器验收的全量回归为 92 项通过、8 项跳过。另行开启百炼的成长导师后端测试组为 9 项通过，含真实的路线讲解、两轮教学、作业评估及固定样例核验。

五组不同背景的账号验证了证据诊断、先修顺序、每日额度、恢复与重试、资料上传、作业版本、不同评分规则、能力升级和回退、同题练习及账号隔离。Edge 验证了路线、完成记录、导师恢复、笔记、作业复盘和阶段测评。本阶段人工核对了真实模型对 SQL 查询粒度、固定样例和复练建议的解释。 [教学与人工复核样例](examples/learning-sql.md)

## 第七阶段验证

开发库与测试库均迁移到 `20261121_0006`，Alembic 检查和前端生产构建通过。跨模块回归 83 项通过、7 项默认跳过。最终评分规则复测中，面试后端 16 项通过，含 2 项真实 GitHub／百炼用例。题库测试涵盖 10 组合成背景与 40 个题例；测试同时检查五种模式、综合七阶段切换、引用和快照、动态追问、超时、重复请求、隐私权限和报告。

Edge 在隔离 API 和 Vite 上验证了注册回跳、开始面试、提交答案、刷新恢复追问、复盘和完成训练任务。真实模型验收使用 yocto-queue 公开提交和虚构作答，同题评分校准另对照四种合成回答。人工核对看到正确简答仍有偏严扣分，技术错误分较低。最终规则隐藏低覆盖单题和总分。 [流程与复测](INTERVIEW.md) · [示例与人工抽查](examples/interview-review.md)

## 第六阶段验证

2026 年 11 月 21 日，本机 MySQL 开发库和测试库均迁移至 `20261121_0005`，Alembic 一致性检查和前端生产构建通过。自动化回归 68 项通过、5 项默认跳过。第六阶段 Edge 浏览器测试经真实 React 和 FastAPI，使用可控的 GitHub 与模型响应，验证了导入、刷新、查看源码、解释、知识检索、导师、答题、成绩与自述。

另行执行两项真实验收并通过。分别导入 Python 的 ItsDangerous、JS 的 yocto-queue、TS 的 is，并以 yocto-queue 运行百炼架构、解释、出题和评分。之后用同一仓库的缓存快照复测函数解释。人工核对了输出与对应提交的源码。安全自动化覆盖非法地址、私有和不存在仓库的模拟 GitHub 响应、重定向、限流、超限、文件过滤、凭据遮盖、范围引用和用户及版本隔离。 [验收样例](examples/project-mentor-queue.md) · [复测说明](PROJECT_MENTOR.md)

## 第五阶段验证

`tests/test_discovery.py` 覆盖低空经济、国际贸易、教育、零售与物流五组端到端合成用户，包含多轮、背景读取、痛点和证据、项目和 PRD、隔离、重复提交、失败重试、搜索缺配置及空结果。`tests/test_discovery_browser.py` 验证真实页面和 API 的注册、登录、会话刷新、研究、对比项目、保存和下载。受控搜索响应校验 Tavily 接口发送的一般请求，真实联网验收需有效密钥。 [第五阶段复测方式](PRODUCT_DISCOVERY.md)

2026 年 11 月 21 日，本机 MySQL 开发库与测试库迁移至 `20261121_0004`，Alembic 模型一致性检查通过，前端生产构建通过。自动化回归 52 项通过、3 项跳过，其中第五阶段浏览器测试通过。另行启用真实百炼合成用例后通过 1 项。人工核对了其竞品报告中引用的 n8n 官方原文。Tavily 实际联网请求仍待配置后复测。

## 第四阶段验证

迁移隔离测试库后运行 `pytest -q tests/test_api.py tests/test_resumes.py tests/test_jobs.py`。岗位测试覆盖十组评分参考、任务去重、权限、错误重试、岗位删除和历史报告。浏览器启用 `CAREER_LIVE_JOB_E2E=1` 后使用合成 JD 实测解析和建议。模型指标和复算方式见 [岗位匹配说明](JOB_MATCHING.md)。

## 第三阶段验证

先在隔离测试库运行到当前 Alembic 版本，从 `backend` 目录执行：

```powershell
$env:APP_ENV = 'test'
$env:DB_NAME = 'career_copilot_test'
& .venv/Scripts/python.exe -m pytest -q tests/test_api.py tests/test_resumes.py
```

简历接口测试使用真实 MySQL 和可控制的模型响应，涵盖十份文件解析、超限与错格式、扫描版无文字、跨账户读写、删除与任务并发、模型格式错误／超时、用户确认和报告历史。真实模型抽验方法和样本指标见 [RESUME_AI.md](RESUME_AI.md)。

浏览器复测需启动使用测试库的 FastAPI、Vite 和单独的 worker。API 和 worker 的 `RESUME_STORAGE_DIR` 要指向同一个专用测试目录，FastAPI 的 `CORS_ORIGINS` 需含测试前端地址。设置 `CAREER_E2E_URL` 与 `CAREER_BROWSER_CHANNEL` 后，`CAREER_LIVE_RESUME_E2E=1` 会启用 `tests/test_career_browser.py`。该测试会将一份项目生成的合成 DOCX 发送给配置的模型。

本阶段最终运行通过 30 项后端测试和 2 项 Edge 浏览器测试，覆盖第二阶段账户回归与第三阶段真实百炼流程。真实模型浏览器测试经历上传、本地解析、核对脱敏文本、结构化提取、确认、画像、优化、保存和删除。前端类型检查与生产构建通过，两个 MySQL 库均在 `20261120_0002`。

## 第二阶段自动化验证

在项目根目录安装测试依赖，使用独立测试库迁移和验收：

```powershell
& backend/.venv/Scripts/python.exe -m pip install -r backend/requirements-test.txt
$env:APP_ENV = 'test'
$env:DB_NAME = 'career_copilot_test'
& backend/.venv/Scripts/python.exe -m alembic -c backend/alembic.ini upgrade head
Set-Location backend
& .venv/Scripts/python.exe -m pytest -q tests/test_api.py
```

浏览器测试需要 MySQL 在运行、Vite 按 README 启动、FastAPI 使用以上测试环境变量指向测试库。Windows 本机可使用已安装的 Edge：

```powershell
# 在 backend 目录
$env:CAREER_E2E_URL = 'http://127.0.0.1:5173'
$env:CAREER_BROWSER_CHANNEL = 'msedge'
& .venv/Scripts/python.exe -m pytest -q
```

如果使用 Playwright 管理的 Chromium，可以在项目可写位置设置 `PLAYWRIGHT_BROWSERS_PATH` 后执行 `python -m playwright install chromium`，并清除 `CAREER_BROWSER_CHANNEL`。测试会使用随机示例邮箱向测试库写入测试记录。缺少测试地址时跳过浏览器测试。

| 范围 | 检查 |
| --- | --- |
| 认证 | 注册、重复邮箱、错误邮箱、弱密码、密码哈希检查、登录、错误密码、缺失／无效／过期令牌 |
| 档案 | 首次保存、更新、查询、未创建、双用户隔离、拒绝客户端提交用户 ID、并发首次保存 |
| 安全 | Cookie 属性、CSRF、CORS、注销、基础限流 |
| 端到端 | 未登录跳转、注册、登录后进入驾驶舱、刷新恢复、建档和编辑、驾驶舱真实字段更新、退出 |

本阶段实测环境为 Windows、Python 3.14.8、MySQL 8.4.13 和 Microsoft Edge。最终运行共 16 项通过，包含真实 MySQL API 测试及浏览器端到端测试。开发库与测试库的迁移均位于 `20261120_0001`，Alembic 未检测到模型与表结构差异，前端类型检查与构建通过。

## 第一阶段界面回归

从项目根目录运行 `npm.cmd --prefix frontend run typecheck` 和 `npm.cmd --prefix frontend run build`。再启动 `npm.cmd --prefix frontend run dev`，在浏览器验收。

| 场景 | 验收结果 |
| --- | --- |
| 首页和数据标记 | 六个区域可见，求职概览中的示例字段和能力数据有演示标记 |
| Sidebar 导航 | 每个入口可达，页面标题、面包屑和当前项一致 |
| 驾驶舱入口 | 欢迎按钮与五张卡片进入对应的「待开发」页面 |
| 任务状态 | 可勾选和取消，计数随之变化，刷新后保留 |
| 顶部入口 | 搜索可过滤和跳转，通知打开空状态，登录后头像进入个人档案 |
| 子页面刷新 | 地址和标题保持一致，未识别路径回到驾驶舱 |
| 响应式 | 1440px、1024px 和 768px 下可用，窄平板可以展开侧栏导航 |
| 键盘操作 | Tab 可到达导航和任务，Space 切换任务，Escape 关闭打开的搜索或通知面板 |

## 第九阶段求职执行

在隔离 MySQL 测试库运行 `tests/test_applications.py`。五组新账号分别走完整 API 链路，覆盖手动及 JD 录入、收藏筛选、原有匹配引擎、简历版本更新与权限、投递状态历史、并行日程冲突检查、历史快照、统计及模型失败重试。通过独立 SQL 聚合复算投递、Offer 和面试通过数。浏览器用例 `tests/test_applications_browser.py` 验收登录回跳、场景交互、看板拖动、页面刷新、日程链接、策略结果和 820px 布局。实际模型测试需设置 `CAREER_PHASE9_LIVE=1`，发送的仅是五条合成投递的匿名汇总。运行方式见 [第九阶段使用与复测](JOB_APPLICATIONS.md)。

本轮回归使用 MySQL 和 Edge，101 项通过，9 项按配置跳过。单独启用阿里云百炼策略测试后，1 项通过。开发库和测试库均迁移至 `20261121_0009`，两库均通过 `alembic check`。React 类型检查及 Vite 生产构建通过。
