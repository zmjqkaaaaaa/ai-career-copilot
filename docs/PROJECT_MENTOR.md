# 第六阶段 · 项目工作台

从本地应用登录后打开「项目工作台」，粘贴公开仓库首页链接。项目首次导入会读取元数据、默认分支最新提交、文件树和精选文本。GitHub API 提供这些信息的结构化响应，可以用提交 SHA 相当于一次版本的唯一编号。更新仓库时可以在版本选择器切回旧提交，旧提交上的解释、答题与报告会保留。

## 操作和教学

1. **架构概览**先看已读文件数和技术栈依据。React、FastAPI 等依赖来自清单，常见入口文件名和数据库模型名称仅提示搜索方向。架构分析使用已读片段，结论可展开跳回原代码。
2. **代码阅读**在树中选 `main.py` 一类的入口，再找路由函数。例如找到 `@app.get(...)`，看它调用哪个函数，然后顺着导入关系找到定义。Python AST 和 TypeScript 编译器解析代码的语法结构。AST 的函数节点保留名字、起止行和调用名称，可以在浏览器标注行号。跨文件导入与运行时实际调用分别记录。
3. **知识库与导师**按文件名、函数、类或关键词找一小组代码片段。问「某个函数为何先校验输入」或「这个 API 结果怎样存入数据库」，阅读引用和待验证说明。检索增强生成（RAG）先找资料，再用这些资料生成回答。本项目用文件、符号和关键词索引，也能在有明确函数名时提供可复核证据。查询找不到代码时，先打开对应文件加入索引。
4. **理解测试**可选择概念、函数、流程、选型、Debug、架构或修改方案题。示例问题「队列为空时，`dequeue` 如何处理？」评分点可以要求复述空值分支和返回值。后台核对每项评分点，完整得 1 分，部分得 0.5 分，错误或缺失得 0 分，再归一化到 100 分。
5. **掌握报告**显示实际答题、用户自述、据答题推断的薄弱项和待测试能力。单维度 75 分是项目采用的练习通过线；扩展能力只记录为书面练习，实践前应实际修改一项本地练习代码并运行测试。

## 关键文件

| 文件 | 作用 |
| --- | --- |
| `backend/app/services/github_service.py` | GitHub HTTPS 只读请求、域名和 URL 校验、配额和大小限制 |
| `backend/app/services/codebase_parser.py`、`backend/tools/index_js.cjs` | 清单选择、Python 与 JS/TS 静态解析、源代码行范围、凭据标记遮盖 |
| `backend/app/services/project_knowledge_service.py` | 依赖证据、入口推断、导入关系、符号和关键词检索、片段预算 |
| `backend/app/ai/code_project_prompts.py` | 架构、函数解释、导师、出题和打分的结构化提示词 |
| `backend/app/services/code_project_workflow.py` | 版本隔离、预览签名、任务取出与保存、基于评分点计算分数 |
| `backend/app/models/code_project.py`、`backend/app/api/v1/endpoints/code_projects.py` | 存储和当前账号可访问的接口 |
| `frontend/src/pages/ProjectWorkspacePage.tsx`、`frontend/src/components/mentor/CodeEvidence.tsx`、`frontend/src/services/codeProjects.ts` | 路由页、树和代码引用、请求服务 |

## 数据与安全

初次导入最多读取十个核心文本。仓库限制 20 MiB，树最多 2,000 条，单文件 128 KiB，一份提交最多缓存 40 个文件和 3 MiB 内容。按仓库对象 SHA 取回不可变文本。默认匿名读取 GitHub，正常为每来源 IP 每小时 60 次，界面可在 GitHub 有提供时显示额度恢复时间。常见密钥、环境文件、二进制和符号链接经过过滤；疑似凭据和私钥块保留行号并遮盖。检测只能覆盖已实现的路径和文本模式，用户可在模型请求前核对片段。

仓库源文件作为字符串交给静态解析器。模型上下文最多包含 10 个索引片段、约 12,500 个代码字符，外加调用所需字段；统一 Provider 仍限制总输入与输出。确认凭据绑定账号、快照、任务、输入与服务配置。代码中的指令视为代码数据，模型响应进入 Pydantic 校验，并核对引用编号映射到本快照片段。引用支持人工理解原文，具体解释仍可对照代码复核。
 
## 数据库迁移与验证

从项目根目录运行。已有项目工作台使用原来的 Vite、FastAPI 和 Worker 启动命令。需安装前端依赖，后端在静态解析 JS/TS 时会用该项目已安装的 TypeScript。

```powershell
Set-Location backend
& ./.venv/Scripts/python.exe -m alembic upgrade head
$env:APP_ENV='test'
$env:DB_NAME='career_copilot_test'
& ./.venv/Scripts/python.exe -m alembic upgrade head
& ./.venv/Scripts/python.exe -m pytest -q
```

`CAREER_LIVE_PROJECTS=1` 开启真实 GitHub 与百炼测试，可用 `CAREER_PROJECT_REPORT_DIR` 保存报告。`CAREER_PROJECT_BROWSER=1` 开启浏览器验收，搭配 `CAREER_E2E_URL` 指向隔离前端，并可用 `CAREER_BROWSER_CHANNEL=msedge` 选择 Edge。实测覆盖范围记录于[测试计划](TEST_PLAN.md)。

[队列项目示例](examples/project-mentor-queue.md)包含人工核对的架构、函数、测验与报告。完整真实结果保存在本机 `work/phase6/public-project-acceptance.json`。同一测试库跑过仓库验收后，可以设置 `CAREER_LIVE_MENTOR_REVIEW=1` 复测函数级解释。该复测使用已缓存的公开快照，结果保存为 `work/phase6/focused-code-explanation.json`。
