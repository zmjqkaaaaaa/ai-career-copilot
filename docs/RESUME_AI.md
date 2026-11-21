# 第三阶段简历 AI 使用与评测

## 配置模型服务

在本地 `backend/.env` 配置以下参数，实际密钥由部署者填写：

```dotenv
LLM_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
LLM_MODEL=deepseek-v4.1-flash
LLM_API_KEY=<你的阿里云百炼 API Key>
LLM_JSON_MODE=json_object
LLM_THINKING=disabled
LLM_THINKING_FORMAT=enable_thinking
LLM_TIMEOUT_SECONDS=75
LLM_MAX_TOKENS=5500
LLM_MAX_INPUT_CHARS=36000
```

上述地址为百炼华北2（北京）的 OpenAI 兼容共享地址。其他地域或业务空间可按百炼控制台提供的地址配置。修改后重启 FastAPI 与任务进程。项目的真实调用使用百炼而非 DeepSeek 自营端点。 [百炼 Base URL](https://help.aliyun.com/zh/model-studio/base-url) · [百炼 DeepSeek 调用](https://help.aliyun.com/zh/model-studio/deepseek-api)

API Key 用来给第三方模型请求认证，只应存在于本地环境。真实简历先经本地解析，用户主动确认提交后，脱敏文本才会发给配置的模型服务。脱敏可遮盖常见联系方式和已有字段标记，用户预览仍是校对姓名等内容的环节。

## 页面与代码

1. 进入「AI 职业画像」，上传文件并点击「本地解析」。PDF 提取文字层，DOCX 遍历段落和表格。源码为 `services/resume_parser.py`。
2. 在脱敏预览中隐藏不适合发送的段落，再发起结构化提取。核对八类条目，必要时修改再确认。模型输出结构由 `schemas/career.py` 定义。无原文可核对的用户补充条目留在本地供用户参考。
3. 切到「职业画像」，选择目标岗位并生成报告。直述的能力、从经历推断的能力和证据不足分别展示。要证明能力已经通过测试，必须有独立验证记录。图表只是能力状态的条目统计。
4. 切到「优化建议」，核对原句、建议稿、原因和可能追问。确认时保存单独的文本稿。

### 模型为什么需要两层检查

`ai/prompts.py` 为提取、分析和优化分别定义任务和版本。Prompt Engineering 是明确任务和证据规则的设计过程。Structured Output 是模型按 JSON 结构返回的结果。Pydantic 检查键名、数据类型与允许的状态，`ai/evidence.py` 则检查引用是否在指定段落。模型仍可能在标准化文本或者建议里作出不受支持的解释。证据检查、待补证标记和人工确认一起降低把这些解释误写成事实的风险。

模型调用默认 75 秒超时，单次输出上限 5500 Token。任务重复点击可复用。每个账号的 AI 请求按小时控制，失败后的再次调用需要手动触发。日志使用状态、耗时、用量，避免记录完整原文、模型回答和密钥。

## 自动化复测

测试样本定义和预期内容在 `backend/tests/fixtures/resume_cases.json`。生成并运行真实模型评测：

```powershell
Set-Location backend
$env:PYTHONPATH = (Get-Location).Path
& .venv/Scripts/python.exe tests/evaluate_resume_model.py --output ../work/phase3/model-evaluation.json
```

十份 PDF/DOCX 均为合成材料。参考条目来自样本编写时预先定义的内容，可逐条复核。检测指标是样本内参考词条匹配和引用定位，没有使用真实求职者数据或独立人工标注团队。每次重跑会调用模型并产生相应计费。

| 实测项目 | 百炼 `deepseek-v4.1-flash` 第一次完整评测 |
| --- | --- |
| 院校参考词条 | 10/10 |
| 技能参考词条 | 15/15 |
| 项目参考词条 | 7/7 |
| 实习参考词条 | 2/2 |
| 预期为空但出现条目的类别 | 0 |
| 三份职业报告的 SQL 状态 | 3/3；两份简历自述，一份证据不足 |
| 三份优化报告 | 13 条建议，9 条标为待补证，其中 1 条触发数字或职责规则并退回原句 |

这组结果反映小规模合成样本上的表现。复杂版面、扫描 PDF、真实简历多样性和优化建议的全面语义真实性需要单独测量。扫描 PDF 的 OCR 在本阶段范围之外。
