# 第五阶段 · 产品探索与 PRD

## 从一个经历走到第一版需求

1. 在「兴趣探索」创建会话，选引导或辅助模式。页面会显示本人的档案、最新确认能力和岗位差距摘要。填写每周可投入工时，让后续推荐能估算开发周期。
2. 用最近一次经历回答导师。比如「上次核对哪些记录，耗时多久，当时用了什么工具？」每轮将近 12 条历史消息中的相关内容与背景一起发给模型。模型返回解释、一条学习提示和最多两道问题。自述兴趣须能回到原消息，推断的兴趣可由本人修正并确认。
3. 在「痛点工作台」提取痛点。把时间、场景、用户群、现在的方法和代价拆开记。亲历、观察与转述对证据的强度不同，AI 的结论会留下待验证状态。访谈可问上次发生了什么、用了什么替代方法、为解决问题已经付出多少。先听叙述，再核对是否反复发生和是否值得解决。
4. 在「市场研究」填写公开搜索词或补录已读的公开原文。对比竞品时查看其服务对象、已核对的能力、使用条件及目标用户当前的替代方法。每项事实保留原文和来源，不足部分列为待验证。竞品存在本身只能说明它提供某种产品能力。
5. 在「机会评估」核对机会分、证据覆盖率、差异化和验证计划。进入「项目推荐」可以比较方案、收藏、修订、重新生成和选定。PRD 记录目标与范围、流程、AI 输入输出与失败处理、数据、风险和验收标准。保存会新增版本，可以查看和导出 Markdown。

## 临摹关键代码

```text
backend/
  app/api/v1/endpoints/discovery.py    HTTP 接口与所属账号校验
  app/ai/discovery_prompts.py          六类 AI 任务的提示词
  app/models/discovery.py             MySQL 数据模型
  app/schemas/discovery.py            输入和输出结构
  app/services/                       对话、痛点、市场、评分与任务处理
  alembic/versions/20261121_0004_add_product_discovery.py
  tests/test_discovery.py
  tests/test_discovery_browser.py
frontend/src/
  pages/ProductDiscoveryPage.tsx      兴趣探索与项目推荐
  components/discovery/               工作台编辑控件
  services/discovery.ts               请求后端、状态与类型
```

| 文件 | 阅读方法 |
| --- | --- |
| `backend/app/ai/discovery_prompts.py` | 看 `PAIN` 如何要求模型逐字引用消息、区分亲历与转述、给出中立访谈题。再看 Pydantic 同名契约怎样限制内容。 |
| `backend/app/services/discovery_workflow.py` | 跟一条请求从预览、确认、入队、处理走到持久化。Python 固定步骤和输入，数据库保证任务可以追踪。模型在每个步骤产出文本与结构。 |
| `backend/app/services/competitor_analysis_service.py` | 用编号关联来源，核对引用片段确实出现在该来源；用浏览器打开来源检查声明是否真的被支持。 |
| `backend/app/services/opportunity_evaluation_service.py` | 改一条评价的证据类型，观察评分和覆盖率的变化。 |
| `backend/app/services/project_recommendation_service.py` | 看背景与能力差距如何进入模型，Python 怎样过滤相同方向并按工时排序。 |
| `frontend/src/pages/ProductDiscoveryPage.tsx` | React 把会话 ID 放入 URL，轮询任务状态并重新读取保存的数据。API 模块集中管理请求。 |

固定工作流的步骤由用户触发并由后端决定。自主 Agent 会根据目标自行选择要执行的工具和下一步。当前流程由用户先核对外发字段，后台按批准内容执行；同一提交复用任务，最多尝试三次。改变模型设置或过期预览后需要重新核对。

## 机会分和推荐规则

需求强度、岗位相关性各占 15；频率、现有成本、竞品覆盖缺口、差异化、可行性、能力适配、展示价值各占 10。每项为 0–4 分。Python 只计入引用了该维度接受的真实证据类型的评分。分数等于有效项的「权重 × 评分 ÷ 4」之和除以有效权重之和，再乘 100。有效权重之和就是证据覆盖率。如果没有合格引用，分数显示「证据不足」。分数 100、覆盖率 15% 只说明一项有证据的维度得满分。推断和未知保留供后续访谈验证。

模型以专业、技能、兴趣、求职目标、岗位差距和机会报告生成 3–5 个方案。Python 检查方向、名称及功能与交付物是否重复，以四周乘每周工时作为可投入时间的参考，优先排列适合时间预算的项目，再按预估工时排序。工时由模型估算，项目价值需要用户判断。

## 外部搜索与资料质量

在本机 `backend/.env` 设置 `TAVILY_API_KEY`，重启 API 与 Worker。每次审核并确认后，最多发送三条用户输入的查询词，使用 Tavily Basic Search。账号计费以实际计划为准。 [Tavily Search 接口](https://docs.tavily.com/documentation/api-reference/endpoint/search) · [Tavily 用量说明](https://help.tavily.com/articles/8298987937-billing-credits-usage-limits)

手动资料保留 URL、标题、公开原文、类型及收集时间，页面标注来自用户补录。搜索返回的摘录同样可回查。没有资料或资料不能支撑竞品结论时，页面提示证据不足。引用校验只能验证所给文字中是否出现摘录；页面内容变更、结论是否合理以及资料时效需要人工复核。

[竞品研究示例](examples/discovery-competitor.md) 记录了如何比较案例现有流程与 n8n。实际百炼验收产出的 JSON 报告和 17 节 PRD 保存在本机 `work/phase5`。人工比对确认 n8n 引文支持工作流编排能力，用户规模、商业模式和低空巡检需求仍缺少这份材料的证据。

## 本地迁移与复测

从项目根目录执行 PowerShell。使用独立测试数据库运行测试。

```powershell
Set-Location backend
& ./.venv/Scripts/python.exe -m alembic upgrade head
$env:APP_ENV='test'
$env:DB_NAME='career_copilot_test'
& ./.venv/Scripts/python.exe -m alembic upgrade head
& ./.venv/Scripts/python.exe -m pytest -q
```

真实模型测试仅使用合成案例和手动核对的公开来源，需要显式设置 `CAREER_LIVE_DISCOVERY=1`，可选用 `CAREER_DISCOVERY_REPORT_DIR` 导出样例。浏览器回归通过独立的 Vite 和 API 实例，使用 `CAREER_DISCOVERY_BROWSER=1`、`CAREER_E2E_URL` 和可选 `CAREER_BROWSER_CHANNEL`。工作区没有 Tavily 密钥，联网搜索验收待配置后完成。
