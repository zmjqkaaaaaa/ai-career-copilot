# 第七阶段 · AI 模拟面试

登录后打开「AI 面试训练」。在准备页选择岗位、简历、项目或仓库提交，核对安排并创建。点击「预览并开始面试」，核对本次发送资料后确认。每次回答可以预览，后台完成分析后显示下一题。刷新或从「面试历史」再次进入可继续；倒计时按服务器截止时间计算。结束后可从报告找到训练任务，并在训练中心标记完成。

## 五种面试模式

| 模式 | 阶段 | 一道可练习的题 |
| --- | --- | --- |
| 简历深度 | 自我介绍和简历经历，需要已确认简历 | 选一段经历，说明你负责的部分和怎样验证结果 |
| 项目深度 | 项目需求、核心流程、代码、测试、个人贡献 | 对照已导入提交，说明函数输入和返回值 |
| 产品思维 | 产品判断、场景设计 | 如何验证用户愿意使用求职助手的首版 |
| AI 技术 | LLM、提示词、RAG、Agent 和 AI 应用工程 | 模型返回错误 JSON 时应如何检测与处理 |
| 综合模拟 | 自我介绍、简历、项目、产品、技术、场景、反问 | 从不同知识主题逐段练习，可手动分配阶段用时 |

正式模式只展示题目和必要的资料来源。教学模式允许显示提示。项目代码不足时，会引用允许使用的背景或显示假设情境。仓库源码、学习测验和用户贡献声明是不同证据。

## 状态与模型调用

`ready → in_progress → finished`。第一道题保存时开始计时，刷新不重置时间。每个回答绑定一题，问题排序和父题由数据库保存。遇到新答案时，模型可以建议追问、验证错误概念、推进或结束当前阶段。服务端检查追问是否引用原回答、是否重复、该主题是否追问过、剩余题量与时间。全部阶段完成、倒计时结束或用户选择退出后，服务端汇总已有结果。超时或输出无法解析时，原任务最多重试三次，保留原确认范围。

AI 面试官在每轮依据模式、岗位、当前题和相关证据给出问题或判断。模型输入保留最近的少量题目和考察主题，并用明确的资料编号引用简历、JD、PRD 或代码。模型一次同时返回当前题的评分依据和拟追问，控制每场调用次数。用户可在页面核对发给百炼的资料和答复。历史报告与训练任务由 Python 汇总，无需重复向模型发送完整会话。

## Rubric 与效果检查

规则表按通用 40%、题型 60% 分配。产品题看用户、需求、方案、排序、价值和指标。技术题看概念、原理、实现、取舍与异常。项目题看业务、贡献、架构、实现、验证和反思。行为题看情境、任务、行动、结果和反思。

每项用 0–4 判断。0 表示回答显示有核心错误或未回应，1 表示提到相关内容但存在关键错误或遗漏，2 表示方向基本正确而缺重要分析，3 表示准确且剩少量细节，4 表示该维度的解释准确完整且有依据。Python 每级乘 25 转换成百分制，按有原回答引用的维度加权，并单独统计覆盖率。单题和整场覆盖不足 50% 时各自暂不报分，低覆盖单题也不会计入总分。评分供个人练习参考。人工复核可以对照同一道题的不同答法，核对引用、评分缺项、概念错误以及建议能否实际执行。

历史复盘根据同岗位最近五场是否反复出现同一个薄弱主题，安排最多四项训练。任务包含具体动作、复练问题、验收方法和下次目标。项目理解可用自己的话解释实现、对照源码走读，并用可复现的测试验证，不能仅凭复述判定已独立完成项目。

## 对照代码阅读

| 文件 | 阅读内容 |
| --- | --- |
| `backend/app/services/interview_preparation_service.py` | 从已确认简历、JD 和代码索引读取当前账号的资料，固定版本和来源标签。 |
| `backend/app/ai/interview_prompts.py` | 开场与动态追问 Prompt，限制一题一问、资料引用和评分锚点。 |
| `backend/app/services/interview_engine.py` | 跟一次请求从预览、签名、排队到保存，查看为什么状态必须由 Python 控制。 |
| `backend/app/services/interview_evaluation_service.py` | 改一条引用，观察它如何影响评分覆盖率。 |
| `backend/app/services/interview_report_service.py`、`interview_training_service.py` | 把多次评分组合为报告，按薄弱项和历史重复程度生成训练。 |
| `backend/app/models/interview.py`、`backend/app/api/v1/endpoints/interviews.py` | 数据表、账号隔离与前端请求。 |
| `frontend/src/pages/InterviewPracticePage.tsx`、`frontend/src/components/interview/InterviewReport.tsx`、`frontend/src/services/interview.ts` | 页面、证据渲染和请求层。 |
| `backend/tests/interview_cases.py` | 十组用户和 20 道产品题、10 道项目追问题、10 道技术题。 |

技术题例子。结构化输出失败时，依次解释 JSON 解析、Schema 校验、受限重试及错误处理。项目追问例子。请对照 yocto-queue 的 `dequeue`，指出输入为空与移除最后一个节点分别触发哪段分支，再说自己是否参与过实现。 [公开仓库源码](https://github.com/sindresorhus/yocto-queue/blob/72a8fa96a9d389765cdf2bb9c6daba8302fc375d/index.js#L38-L53)

## 迁移和复测

```powershell
Set-Location backend
& ./.venv/Scripts/python.exe -m alembic upgrade head
$env:APP_ENV='test'
$env:DB_NAME='career_copilot_test'
& ./.venv/Scripts/python.exe -m alembic upgrade head
& ./.venv/Scripts/python.exe -m pytest -q
```

React、FastAPI 和共享 Worker 的启动方式见 [README](../README.md)。浏览器测试通过 `CAREER_INTERVIEW_BROWSER=1` 和 `CAREER_E2E_URL` 指向隔离前后端。真实 GitHub 与百炼验收通过 `CAREER_LIVE_INTERVIEWS=1` 启用，四组评分对照通过 `CAREER_LIVE_INTERVIEW_CALIBRATION=1` 启用，可设置 `CAREER_INTERVIEW_REPORT_DIR` 保存 JSON 报告。

[面试报告与训练示例](examples/interview-review.md)提供公开代码对照、复盘过程和可检验的练习任务。
