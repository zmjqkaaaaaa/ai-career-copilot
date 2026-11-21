# 第九阶段 · 求职执行工作台

## 使用步骤

1. 在侧栏打开「求职执行」。在「岗位发现」录入招聘信息，或先保存招聘原链接、稍后补上原文。可记录发布时间、招聘状态和来源，缺少信息显示未知。
2. 从岗位详情前往「岗位匹配」。复用第四阶段的 JD 提取、硬性要求确认、证据评分和 AI 建议。更新原始 JD 后，重新确认要求并评分。旧匹配仍可在第四阶段的历史中查看。
3. 在「简历版本」选一份已确认的原简历，查看所选岗位的匹配差距和已有建议，选择原文段落、调整顺序或应用已确认且无需额外证据的表达。确认后保存。创建后续版本会保留旧版，可并排对比。
4. 从岗位详情生成「待投递」卡片。用户在招聘渠道完成投递后，将卡片拖进「已投递」，或在详情中选择状态，并填写变更说明和下一步行动。历史卡片提供岗位、简历版本和日程入口。
5. 在「面试日程」选择投递、时间、时区、时长和面试轮次，录入结果和复盘。从日程进入「模拟面试」时，系统使用该投递保存的原始 JD 和当时绑定的简历版本。进入模型问答前仍需核对发送内容。
6. 在「求职统计」选择投递时段。在「AI 策略」核对将发送给模型的匿名计数，确认之后等待共享 Worker 生成策略。报告同时保存统计快照、模型和提示词版本。

岗位来自用户录入、粘贴的 JD 或手动保存的公开网址。来源状态和发布日期由用户记录。第四阶段录入的岗位会出现在工作台。

## 数据关系和状态

```text
users
  ├─ job_positions ── job_matches
  ├─ resumes ── resume_contents ── resume_versions
  ├─ job_applications ── application_status_history
  │       ├─ job_positions（岗位与历史 JD 快照）
  │       ├─ resume_versions（投递使用的版本）
  │       └─ interview_schedules ── 第七阶段模拟面试入口
  └─ job_strategy_reports
```

- `resume_versions` 的 `series_id` 和 `version_number` 唯一标识一版内容，`previous_id` 串起历史。版本是内容快照，限制直接编辑。原简历删除后，现有投递的独立版本快照保留，已删除来源不能用于创建后续版本。
- 每位用户对同一岗位保存一条投递。保存请求可带同一个请求 UUID 重试，重复岗位、过期表单、相同时段安排会返回明确的冲突。岗位已关联投递时，移除操作改为归档。
- 看板状态为待投递、已投递、笔试、一面、二面、HR 面、Offer、拒绝及撤回。招聘流程允许跳步和纠正状态。首次到达已投递至 Offer 中任一状态会记录实际投递时点，已投递记录不能退回待投递。状态和历史在同一事务写入。
- 真实面试日程按 UTC 保存开始、结束时间，同时保留 IANA 时区。重叠检查使用半开区间 `[开始, 结束)`，相接时间可保存，取消的日程释放时段。
- 求职策略保存输入统计、模型输出和提示词版本。预览令牌绑定用户、统计快照、模型配置，并在十分钟后过期。联系人、公司名、岗位名、会议链接、简历和个人笔记留在应用中。

## 统计口径

按用户选择的 UTC 投递日期取样。统计观察的是该批投递目前记载的结果，用于个人复盘。

| 指标 | 计数 |
| --- | --- |
| 累计投递 | 首次实际投递时间在区间内的记录，含之后撤回的记录 |
| 有效投递 | 累计投递中被用户标记为有效的记录 |
| 简历通过 | 该投递有笔试、面试或有效面试日程的记录，以推进到下一环节作为代用指标 |
| 笔试通过 | 已记录笔试并进入面试的投递，以后续进展作为代用指标 |
| 面试邀请 | 已出现面试阶段或有非取消日程 |
| 面试通过 | 至少一场真实面试明确标记通过，分母是至少一场真实面试已有通过或失败结果的投递 |
| Offer | 状态历史中有 Offer 的投递 |

同一投递在各指标中最多计一次。简历、笔试、面试与 Offer 统计以有效投递为基础。面试邀请率、简历通过率和 Offer 转化率以有效投递为分母。笔试通过率以已记录笔试的投递为分母。每项比例的分母至少为 5，分母不足时显示计数。例：有效投递 1、收到面试邀请 1，显示 `1/1 · 样本不足`。有 5 条有效投递并收到 2 条面试邀请时，显示 `2/5 · 40.0%`。

## 代码怎么衔接

- `job_discovery_service.py` 在原有岗位表上加收藏、筛选和归档。新增岗位不复制已有匹配引擎。
- `resume_version_service.py` 根据确认的简历段落号生成快照，服务端核查段落和优化记录确属原简历，避免请求直接写入新经历。
- `application_tracking_service.py` 将投递状态视为状态机。React 看板发出目标状态和当前版本号，服务端检查版本是否过期，并在同一事务追加事件。刷新后重新从 MySQL 读回。
- `interview_schedule_service.py` 验证时区与时间偏移，按用户串行完成日程重叠查询与写入。模拟面试通过日程 ID 查到投递，并读取对应快照。
- `job_pipeline_service.py` 用投递及状态历史计数。小样本阈值在后端统一处理，页面读取分子、分母和可展示的比例。
- `job_strategy_prompts.py` 指定观察、推断、候选假设和行动四类输出。Worker 只发送已确认的匿名统计，由 Pydantic 检查 JSON 结构。把建议写成可验证的行动，例如补齐某阶段结果并在下一批投递时复算同一口径。

## 本地运行和复测

```powershell
# 项目根目录
& backend/.venv/Scripts/python.exe -m pip install -r backend/requirements.txt
& backend/.venv/Scripts/python.exe -m alembic -c backend/alembic.ini upgrade head
& backend/.venv/Scripts/python.exe -m alembic -c backend/alembic.ini check
```

迁移版本为 `20261121_0009`。按 README 分别启动 FastAPI、Vite 和共享 Worker，打开 `http://127.0.0.1:5173/application-workspace`。启动测试前须将 FastAPI 和测试进程指向同一独立测试库。

```powershell
$env:APP_ENV='test'
$env:DB_NAME='career_copilot_test'
& backend/.venv/Scripts/python.exe -m alembic -c backend/alembic.ini upgrade head
Set-Location backend
& .venv/Scripts/python.exe -m pytest -q tests/test_applications.py
# 使用指向测试后端的前端地址，并加入测试后端的 CORS 白名单
$env:CAREER_APPLICATION_BROWSER='http://127.0.0.1:5199'
$env:CAREER_BROWSER_CHANNEL='msedge'
& .venv/Scripts/python.exe -m pytest -q tests/test_applications_browser.py
```
