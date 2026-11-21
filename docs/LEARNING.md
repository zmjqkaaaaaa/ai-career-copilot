# 第八阶段 · AI 成长导师

登录后打开「成长中心」。先看能力诊断，再生成一条学习路线。进入每日任务开始或暂停，记录实际分钟。按知识点打开导师或资料，从一个具体问题开始。写完作业后核对送给模型的内容，通过反馈修改并保存新版本。最后做阶段测评，对照成长报告里的能力记录。

## 能力模型与先修关系

能力模型由六大类与 12 个稳定知识点构成。知识点记录状态、程度、置信度、时间与证据来源。档案和简历内容按自述或推断处理；JD、产品探索、代码测验、面试报告和 AI 作业反馈影响复习优先级。第六、七阶段成绩继续带来源和适用范围。它们可以指向值得学习的内容，但不能代替当前知识点的独立测评。

课程目录的先修关系是一张有方向的图。例如「LLM 基础 → 提示词与结构化输出 → RAG 检索与评估」。规划器沿先修关系访问，每项知识点只加入一次。已有能力证据、岗位差距、复练记录、兴趣和上版顺序决定优先级。耗时用课程估计除以每周预算，约为可安排周数。AI 路线讲解只能补充例子，实际顺序与时长以 Python 计算为准。作业或测评后按变化重排，条件一致时复用已有版本。

## 每日任务、教学与资料

自动任务从路线中选一项先修已学习或已测评通过的内容，按每日和每周预算分配。分钟数较少时安排单个检查点，例如先手算一组 SQL 结果。完成、重学和实耗时间都保存在任务中。日计划默认以浏览器当天日期展示。

导师使用当前知识点、目标、最近摘要、当前理解题和用户本轮回答，部分主题还带本项目真实函数的限长片段。一次只问一个小题。学完可以把导师解释保存为资料。官方与项目材料由课程目录维护。个人资料支持链接、笔记和 TXT、Markdown、DOCX 上传。DOCX 复用既有格式和解压限制；只保存提取文本。用户链接由用户核对，平台不主动抓取。失效资料不会阻断路线或作业。

## 作业与阶段测评

作业按知识点提供任务目标、练习、资料、验收和评分项。每次新提交生成独立版本，支持文本、Markdown、代码片段、产品分析、PRD、上传文档和 GitHub 链接。评估 GitHub 链接时需同时附实现说明或代码片段。审查 Python 语法使用 AST；SQL 按文本和粒度分析。评估不会执行用户 SQL 或 Python，也不会把语法解析标为运行成功。有范围明确的测试时，可将输入、预期值和实际结果一起提交供复核。

作业评级为 0–4 级，再换算百分制。每项必须有提交原句或确定性的静态错误依据。缺少依据的项保持未知，覆盖低于 50% 隐藏总分。Python 和 SQL 作业可填固定样例结果，由 Python 比较预期值。填报结果与样例不符时，作业保持待修订。评估保存规则和提示版本，区分正确、错误、缺失和修订建议。修改后以新版本重新提交。

阶段测评含系统判分的知识和应用选择题，以及通往作业中心的概念解释、场景分析、代码理解、产品设计和综合实践。开放作业反馈帮你理解和修改，选择题成绩只验证题目覆盖的知识。每个知识点首版有两套独立题；首次或不同题通过才增加验证记录。长期重复同题是练习。重新测评发现退步可以回退为待验证，记录原状态、结果、原因与时间。

成长报告按真实任务记录计算完成率和用户填报分钟数。近期列表展示作业、测评及能力变化。读完资料计入学习进度。个人档案及旧职业画像历史仍可独立查看。

## 文件与教学路线

| 位置 | 作用 |
| --- | --- |
| `backend/app/services/learning_catalog.py` | 六大类、知识点、先修和教学模式 |
| `backend/app/services/learning_plan.py` | 多阶段证据、先修规划、每日预算和版本 |
| `backend/app/ai/learning_prompts.py` | 路线说明、苏格拉底式带练、作业审查 |
| `backend/app/services/learning_workflow.py` | 等待用户确认、异步调用、语法检查和评分 |
| `backend/app/services/learning_assessment.py` | 两套客观题与服务器判分依据 |
| `backend/app/services/learning_resources.py` | 人工维护资料目录 |
| `backend/app/models/learning.py`、`backend/app/api/v1/endpoints/learning.py` | MySQL 模型和受保护接口 |
| `frontend/src/pages/GrowthCenterPage.tsx`、`frontend/src/components/learning/`、`frontend/src/services/learning.ts` | 成长页、进度、教学和 API |
| `backend/tests/test_learning.py`、`backend/tests/test_learning_browser.py` | 测试账号、真实模型和浏览器验收 |

读代码时可以从 `make_path` 的 `visit` 开始。如果把 RAG 加到路线，函数先加入它依赖的提示词课程，再处理 RAG 本身。再读 `submit_assessment`，观察何时创建新的能力事件，为什么读资料和做过的同一组题无法直接晋级。最后看 `preview` 和 `run_learning_once`，理解限制上下文、记录已确认快照及按需调用模型如何减少输入和重复费用。

## 迁移与复测

在项目根目录运行，下次启动仍使用原有的前端、后端和共享 Worker。

```powershell
Set-Location backend
& ./.venv/Scripts/python.exe -m alembic upgrade head
$env:APP_ENV='test'
$env:DB_NAME='career_copilot_test'
& ./.venv/Scripts/python.exe -m alembic upgrade head
& ./.venv/Scripts/python.exe -m pytest -q
```

真实百炼验收使用 `CAREER_LIVE_LEARNING=1`，可用 `CAREER_LEARNING_REPORT_DIR` 保存结果。浏览器验收用 `CAREER_LEARNING_BROWSER=1` 和 `CAREER_E2E_URL` 指向隔离前端。

[SQL 教学与人工复核示例](examples/learning-sql.md)记录了路线顺序、导师问答、任务时间与模型反馈的适用边界。

