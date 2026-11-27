# AI Career Copilot AI 产品评测

阶段 11.6 · 基线复核 · 2026 年 11 月 22 日

## 当前证据

| 证据 | 样本及结果 | 可回答的问题 |
| --- | --- | --- |
| 本轮离线重放 | `career-quality-1`，12/12 固定正例通过，12/12 错误内容被检测，12/12 损坏响应被拒绝 | 当前评测规则能否识别预先设计的错误 |
| 与历史离线基线比较 | 相同数据版本和重放模式，12 个样例的通过状态、Prompt 版本及检查项无变化 | 规则行为是否出现回归 |
| 历史真实模型基线 | 阿里云百炼 `deepseek-v4.1-flash`，12 个合成样本，12/12 通过结构校验，9/12 通过全部业务检查，0 次请求错误 | 样例级真实输出基线；每类一条，适合定位问题 |
| 真人产品验证 | 48 小时内改完一处真实经历、使用同一 JD 复查并解释变化，尚无实测分子或分母 | 产品是否推动用户采取行动 |

真模型基线来自 [第十阶段质量报告](../AI_EVALUATION.md)。本轮运行了离线评测。历史真实调用与本轮固定响应的结果各自比较。评测工具和检查项可核对 [评测入口](../../backend/app/services/ai_evaluation_service.py)、[样本](../../backend/app/evaluations/cases.py) 和 [判定规则](../../backend/app/evaluations/checks.py)。

## 公开评测集

| 评测集 | 包含什么 | 完整样本与运行入口 |
| --- | --- | --- |
| 跨模块 AI 质量 | 12 个合成场景。每个场景带期望证据和通过条件，支持正例、故意错误回复和损坏响应三类离线检查。 | [完整样本及对照构造](../../backend/app/evaluations/cases.py) · [检查规则](../../backend/app/evaluations/checks.py) · [运行工具](../../backend/app/services/ai_evaluation_service.py) |
| 简历解析 | 10 份合成简历的原材料和预期事实。支持生成 PDF 或 DOCX。 | [完整样本 JSON](../../backend/tests/fixtures/resume_cases.json) · [生成样本](../../backend/tests/resume_fixtures.py) · [解析回归](../../backend/tests/test_resumes.py) |
| 岗位匹配 | 10 组基础合成用例，包含 JD 要求、候选人证据、人工标记、预期参考分与证据覆盖率。实际模型评测脚本从这些条目生成合成 JD。 | [完整基础用例](../../backend/tests/job_cases.py) · [专项回归](../../backend/tests/test_jobs.py) · [模型评测脚本](../../backend/tests/evaluate_job_model.py) |

样本覆盖范围有重合，各集分别统计。真实试用见[匿名试用记录](USER_TRIAL_RECAP.md)，逐项失败与修复见[Badcase 分析](BADCASE_ANALYSIS.md)。

## 首轮问题优先级

| 优先级 | 历史失败 | 下轮验证 |
| --- | --- | --- |
| 1 | 简历解析保留了事实，但把一条项目摘要分到其他经历 | 用同一事实分别放在显式项目区和混合段落，分别统计事实召回与分类正确性 |
| 2 | 简历优化无捏造，但未给出可直接采用的保守改写 | 单独核对保留原意、无新增事实和可采用性。用户确认前保留证据引用 |
| 3 | 面试概念题因缺少具体语法被扣分 | 配对设计概念题与实现题，人工先定评分口径，再测同类回答是否被一致评价 |

结合 [PRD](PRD.md) 的首轮场景，优先复核简历证据链对匹配结果和改写动作的影响。更大样本、变化后的模型或提示词实测、延迟和成本测量、真人可用性均待对应评测。

## 离线复现

在 `backend` 目录运行。输出路径可换成已有的本地工作目录。

```powershell
& .venv/Scripts/python.exe -m app.services.ai_evaluation_service --output ../work/phase11/evaluation/fixture.json
& .venv/Scripts/python.exe -m app.services.ai_evaluation_service --compare ../work/phase10/sprint4/fixture-baseline.json ../work/phase11/evaluation/fixture.json --output ../work/phase11/evaluation/fixture-comparison.json
```
