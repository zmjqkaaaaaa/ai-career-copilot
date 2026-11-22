# 第二阶段 API

## 求职驾驶舱

`GET /api/v1/dashboard?day=YYYY-MM-DD` 需要登录。首页传入浏览器本地日期，省略时使用 UTC 日期。响应包含目标岗位、档案创建状态、能力证据分类计数、最近仍对应当前岗位版本的匹配及前四项差距、前三个项目推荐、最多五项当日已保存任务、最近面试报告和各投递状态的数量。接口仅查询当前账户已有记录，不生成学习任务或调用模型。

`next_action` 优先展示用户在未结束投递中保存的行动，然后参考待处理学习任务、面试薄弱项和岗位差距，最后给出入门建议。缺失的单条记录返回 `null`，列表无记录时返回空数组。无效日期返回 422，未登录返回 401。

## 跨阶段数据衔接

- `POST /api/v1/code-projects/import` 可传 `recommendation_id`。获取仓库时返回该关联。`GET /api/v1/code-projects/recommendations/{id}` 读取本人已选方案的名称。
- `POST /api/v1/interviews/prepare` 优先使用仓库关联的方案。显式选择的方案仍有优先权。准备结果包含所采用的简历版本、岗位匹配、PRD 及提交来源。
- 探索会话背景含职业画像和匹配报告的 ID 与版本。成长诊断包含匹配报告、PRD、仓库测验及面试训练任务的来源 ID。

## 第八阶段学习导师接口

基址为 `/api/v1/learning`。模型操作先提交 `kind` 和 `record_id` 预览，教学带 `message`。再带 `approval` 提交对应操作，可重复提交同一个确认值并读取任务结果。

| 方法 | 相对路径 | 作用 |
| --- | --- | --- |
| GET | `/catalog` | 课程、能力和教学模式 |
| GET、POST | `/diagnosis` | 现场诊断和保存证据快照 |
| POST、GET、PATCH | `/paths/generate`、`/paths`、`/paths/{id}` | 生成、查询和调整版本 |
| GET、POST、PATCH | `/tasks/daily`、`/tasks`、`/tasks/{id}` | 获取当日任务、追加任务和更新 |
| POST、GET | `/sessions`、`/sessions/{id}/history` | 创建会话、列出会话和恢复历史 |
| GET、POST | `/resources`、`/resources/upload` | 读取或保存资料，上传使用 multipart |
| GET、POST | `/assignments`、`/assignments/{topic}/submissions`、`/assignments/{topic}/submit`、`/assignments/{topic}/upload` | 作业、提交、上传及版本 |
| POST | `/preview`、`/sessions/{id}/messages`、`/submissions/{id}/evaluate`、`/paths/{id}/coach` | 核对并提交模型任务 |
| GET、POST | `/jobs`、`/jobs/{id}/retry` | 状态和重试 |
| GET、POST | `/assessments`、`/assessments/start`、`/assessments/{id}/submit`、`/assessments/{id}/result` | 测评、中断恢复、交卷与证据 |
| GET | `/progress`、`/reports` | 汇总进度、成绩、作业和能力变更 |

## 第七阶段面试接口

基址为 `/api/v1/interviews`。接口需要现有账号；模型请求需预览确认。重复发送相同请求会复用任务。答案、报告和训练都按会话所属账号隔离。

| 方法 | 相对路径 | 作用 |
| --- | --- | --- |
| GET | `/options` | 获取模式、风格和本人已有来源 |
| POST | `/prepare` | 校验设置，确认资料来源和时间安排 |
| GET、POST | `/sessions` | 历史列表及用 `request_id` 创建会话 |
| GET | `/sessions/{id}`、`/sessions/{id}/current-question`、`/sessions/{id}/progress` | 读取状态、当前题和进度 |
| POST | `/sessions/{id}/preview` | 查看模型主机、待发送内容及有时限的 `approval` |
| POST | `/sessions/{id}/start`、`/sessions/{id}/answers` | 带确认值提交开始或作答，返回 202 |
| GET、POST | `/sessions/{id}/tasks/{task_id}`、`/sessions/{id}/tasks/{task_id}/retry` | 查询状态或重试 |
| POST、GET | `/sessions/{id}/finish`、`/sessions/{id}/report` | 结束并汇总，或查看报告 |
| GET、PATCH | `/training-plans`、`/training-tasks/{task_id}` | 查看训练并更新 `todo` 或 `done` |

缺少资料或表单设置不合法返回 422，资料属于其他账号或报告尚未生成时返回 404，重复使用过期预览、提交旧题或任务在处理时返回 409。

## 第六阶段项目工作台接口

基址为 `/api/v1/code-projects`。以下用 `{id}` 表示账号拥有的项目 ID。只读接口可以带 `commit` 选择快照，默认使用最近导入的提交。需要模型的写入接口，提交包含 `kind`、`commit`、相应字段以及预览返回的 `approval`，成功返回 202。开源文件读取和代码教学均在后台执行。

| 方法 | 相对路径 | 用途 |
| --- | --- | --- |
| POST、GET | `/import`、`/` | 提交公开 URL、列出项目 |
| GET、DELETE | `/{id}` | 读项目及快照、移除本地项目 |
| POST | `/{id}/refresh` | 检查最新提交 |
| GET、POST | `/{id}/files`、`/{id}/files/{file_id}`、`/{id}/files/{file_id}/load` | 文件列表、文本和索引、按需读取 |
| GET | `/{id}/architecture`、`/{id}/knowledge?q=关键词` | 读架构、检索代码证据 |
| POST | `/{id}/preview` | 核对模型目的地与上下文 |
| POST | `/{id}/analyze`、`/{id}/explain`、`/{id}/chat` | 提交架构、解释或导师问答任务 |
| GET | `/{id}/explanations`、`/{id}/chat/history` | 查询解释和问答记录 |
| GET、POST | `/{id}/quizzes`、`/{id}/quizzes/generate`、`/{id}/quizzes/{quiz_id}/submit` | 读题、生成、提交答案 |
| GET、PUT | `/{id}/mastery-report`、`/{id}/mastery-report/self-report` | 汇总掌握情况、提交自述 |
| GET、POST | `/{id}/tasks/{task_id}`、`/{id}/tasks/{task_id}/retry` | 查询状态、重试失败任务 |

其他账号的项目和跨版本文件 ID 返回 404。项目已有进行中的操作、确认内容改变或预览过期时返回 409。GitHub 限流记录在任务状态，供应商给出恢复时间时返回 `retry_at`。

## 第五阶段产品探索接口

下列路径使用 `/api/v1`。登录凭据和 CSRF 约定同前。异步操作先提交预览，再带返回的 `approval` 提交原请求，返回 202。额外查询参数 `session_id` 用于绑定独立业务路径与探索会话。

| 方法 | 路径 | 用途 |
| --- | --- | --- |
| GET、POST | `/discovery/sessions` | 读取或创建会话 |
| GET、PUT | `/discovery/sessions/{id}` | 会话详情与偏好 |
| PUT | `/discovery/sessions/{id}/interests/{interest_id}` | 修正或确认兴趣 |
| POST | `/discovery/sessions/{id}/preview` | 预览脱敏输入并取得确认票据 |
| GET、POST | `/discovery/sessions/{id}/messages` | 读取历史或开启新一轮 |
| POST | `/discovery/sessions/{id}/pain-points` | 提取痛点 |
| GET、PUT | `/pain-points`、`/pain-points/{id}` | 读取列表、编辑痛点 |
| POST、GET | `/research/competitors?session_id={id}`、`/research/competitors/{id}` | 创建研究或读取报告 |
| PUT | `/research/competitors/{id}/records/{competitor_id}` | 编辑竞品并复核引用 |
| POST、GET、PUT | `/opportunities/evaluate?session_id={id}`、`/opportunities`、`/opportunities/{id}` | 评估、列出或修订机会 |
| POST、GET、PUT | `/projects/recommendations`、`/projects/recommendations/{id}` | 生成、读取、编辑、收藏和选定项目；生成时附 `session_id` |
| POST、GET | `/projects/recommendations/{id}/prd`、`/projects/recommendations/{id}/prds` | 为选定项目生成 PRD、读取历史 |
| GET、PUT | `/prds/{id}` | 读历史版本，用最新版本保存修改 |
| GET | `/prds/{id}/markdown` | 以 Markdown 下载该版本 |
| GET、POST | `/discovery/tasks/{id}`、`/discovery/tasks/{id}/retry` | 轮询状态、重试失败任务 |

他人的数据与不存在的数据使用 404。确认内容变更、预览过期、编辑版本落后使用 409。缺少搜索配置时，查询类预览返回 `DISCOVERY_SEARCH_NOT_CONFIGURED`。报告会指明资料的补录或搜索来源。

业务路径以 `/api/v1` 开头。启动 FastAPI 后可查看 [OpenAPI 交互文档](http://127.0.0.1:8001/docs)。React 开发环境的 Vite 服务将同源的 `/api` 请求转发到 FastAPI。

| 方法与路径 | 请求 | 成功 |
| --- | --- | --- |
| GET /health | 无 | 200，`{"status":"ok"}`。这是进程健康检查。 |
| POST /api/v1/auth/register | JSON，`email`、`username`、`password` | 201，账户基本信息 |
| POST /api/v1/auth/login | URL 编码表单，`username` 填邮箱，另传 `password`。兼容 OAuth2 Password 表单 | 200，`{"access_token":"…","token_type":"bearer"}` |
| POST /api/v1/auth/session | 与登录相同的表单，附带浏览器来源和 CSRF 请求头 | 200，账户基本信息和 HttpOnly Cookie |
| DELETE /api/v1/auth/session | 浏览器来源和 CSRF 请求头 | 204，清除 Cookie |
| GET /api/v1/users/me | Bearer 或 Cookie | 200，当前账户基本信息 |
| GET /api/v1/profiles/me | Bearer 或 Cookie | 200，当前账号的档案 |
| PUT /api/v1/profiles/me | Bearer 或 Cookie，完整 JSON 档案。Cookie 写入需 CSRF 请求头 | 200，保存后的档案 |

登录表单的 Content-Type 为 `application/x-www-form-urlencoded`。拿到 Bearer Token 的客户端在后续请求中传 `Authorization: Bearer <token>`。浏览器端会话入口用 `X-CSRF-Protection: 1`，并校验浏览器发出的 `Origin`。账户和档案读写响应使用 `Cache-Control: no-store`。

## 字段与语义

- 账户响应包含 `id`、`email`、`username`、`is_active`、`created_at` 和 `updated_at`。
- 注册密码为 12–128 个字符，包含字母以及数字或符号。用户名去掉两端空白后为 2–64 个字符。
- 档案支持 `real_name`、本科院校／专业／学历、研究生院校／专业、`graduation_year`（1900–2100）、`target_position`、`interested_industries`、`skills`、`internship_experience` 和 `project_experience`。详细字段名和长度见 OpenAPI。前两种列表为字符串数组，两种经历为 `{title, description}` 对象数组。
- PUT 为整份替换。省略可选文本和年份会写入 `null`，省略数组会写入 `[]`。响应额外含档案 ID 和创建／更新时间。时间字段以 UTC 写入数据库并读出。账户归属始终由后端从令牌确认。

## 失败响应

```json
{
  "error": {
    "code": "PROFILE_NOT_FOUND",
    "message": "尚未创建个人档案",
    "details": []
  }
}
```

| 状态 | 常见错误 |
| --- | --- |
| 401 | `NOT_AUTHENTICATED`、`INVALID_CREDENTIALS` |
| 403 | `INVALID_ORIGIN`，Cookie 写入来源或请求头校验失败 |
| 404 | `PROFILE_NOT_FOUND`，首次建档前可预期 |
| 409 | `EMAIL_EXISTS` |
| 422 | `VALIDATION_ERROR`，详情仅含字段名和错误类型 |
| 429 | `RATE_LIMITED`，按 `Retry-After` 等待 |
| 500 | `INTERNAL_ERROR`，服务遇到意外错误 |
| 503 | `DATABASE_UNAVAILABLE`，数据库操作暂不可用 |

当前访问令牌默认生存 30 分钟，过期后需重新登录。退出会清除浏览器会话 Cookie。独立签发的 Bearer Token 继续由其过期时间约束。

## 第三阶段简历与职业画像

以下路径均使用 `/api/v1` 前缀、现有认证与统一错误结构。Cookie 写入请求继续发送 `X-CSRF-Protection: 1`。

| 方法与路径 | 请求和结果 |
| --- | --- |
| POST /resumes/upload | `multipart/form-data` 的 `file` 字段，PDF 或 DOCX，上限 10 MB。返回 201 和元数据。 |
| GET /resumes、GET /resumes/{id} | 当前用户的简历列表或详情。列表支持 `offset`。 |
| DELETE /resumes/{id} | 清理文件和关联记录。成功 204，活动任务期间 409。 |
| POST /resumes/{id}/parse | 可选 `reparse`、`retry`，本地解析任务返回 202。 |
| GET /resumes/{id}/content | 最新内容版本，或指定 `content_id`。尚无内容返回 404。 |
| GET /resumes/{id}/preview | 用 `content_id` 获取可审查的脱敏文本块。 |
| POST /resumes/{id}/extract | 接收 `content_id`、`hidden_blocks` 和可选 `retry`，返回 202。 |
| PUT /resumes/{id}/content | 提交当前 `content_id` 和修改过的 `structured_data`，返回确认后的版本。 |
| POST /career/analyze | 接收 `resume_id`、确认过的 `content_id`、`target_direction` 和可选 `retry`，返回 202。 |
| GET /career/analyses | 返回报告列表，支持 `resume_id`、`offset`。 |
| GET /career/provider | 返回提交前展示的模型和接收文本的主机名。 |
| GET /career/profile | 最新报告，或用 `analysis_id`、`resume_id` 筛选。含能力、状态和原文证据。 |
| POST /resumes/{id}/optimize | 接收已确认的 `content_id`、`target_direction` 和可选 `retry`，返回 202。 |
| GET /resumes/{id}/optimizations | 优化建议与已确认文本，支持 `content_id`。 |
| POST /resumes/{id}/optimizations/{record_id}/confirm | 提交 `text` 保存独立文本版本。 |
| GET /resumes/{id}/jobs、GET /resume-jobs/{job_id} | 任务进度，包含 `queued`、`running`、`succeeded` 或 `failed`。 |

文本解析、结构化提取和报告是三个步骤。上传或提取结果未确认时，对依赖确认版本的操作返回 409。格式无效返回 415，超过大小上限返回 413，账号达到 AI 请求上限返回 429。已排队任务的模型超时、认证错误和结果格式错误通过任务状态及 `error_code` 返回。

三个模型操作均需要 `accept_external_processing: true` 和预览时展示的 `provider_host`。Worker 发出请求前会核对任务保存的脱敏文本摘要和模型配置。
# 第四阶段岗位匹配接口

以下路由使用 `/api/v1` 前缀，并要求当前用户认证。

| 接口 | 功能 |
| --- | --- |
| `POST /jobs/import` | multipart 文件导入，支持 TXT、PDF、DOCX，上限 2 MB。返回预览文本。 |
| `POST /jobs`、`GET /jobs` | 创建岗位和读取当前用户名下的岗位列表。 |
| `GET /jobs/{id}`、`DELETE /jobs/{id}` | 详情含职责、要求和任务。删除成功返回 204。 |
| `GET /jobs/{id}/parse-preview`、`POST /jobs/{id}/parse` | 预览脱敏 JD 和主机名，确认后提交解析任务。 |
| `PUT /jobs/{id}/requirements` | 用版本号核对并确认 JD 要求。 |
| `GET /jobs/candidate-versions` | 获取当前用户已确认的简历版本。 |
| `POST /jobs/{id}/match`、`GET /jobs/{id}/match` | 指定岗位版本、简历内容 ID 及可选的逐项自评，计算或读取匹配报告。 |
| `GET /job-matches`、`GET /job-matches/{id}/gaps` | 获取报告历史和差距。 |
| `GET /job-matches/{id}/recommendations-preview`、`POST /job-matches/{id}/recommendations` | 预览脱敏摘要并提交建议生成任务。 |
| `GET /job-analysis-tasks/{id}` | 读取当前用户任务的状态和失败代码。 |

模型请求需要 `provider_host` 和 `accept_external_processing: true`。返回 202 和可轮询的任务。活动任务与删除冲突时返回 409。评分输出含各维度权重及分数、硬性提示、覆盖率和逐项证据。详细规则见 [岗位匹配说明](JOB_MATCHING.md)。


## 第九阶段求职执行

以下路径使用 `/api/v1`。所有接口使用现有会话鉴权，Cookie 写请求需要 CSRF 请求头。

| 接口 | 请求与返回 |
| --- | --- |
| `GET /jobs` | 通过 `q`、`company`、`title`、`city`、`industry`、`education`、`skill`、`published_from`、`published_to`、`favorite` 筛选，使用 `offset` 分页。 |
| `POST /jobs/import-jd` | 提交 `position_name`、JD 或 HTTP(S) 原链接和可选 `metadata`，返回 201 和岗位。来源只是链接时可稍后补 JD。 |
| `PATCH /jobs/{id}` | 更新 `favorite`、`metadata` 或整份 `job` 内容。更新 JD 后需重新确认要求。 |
| `DELETE /jobs/{id}` | 成功返回 204，已有投递的岗位进入归档。 |
| `POST /resume-versions/preview` | 输入 `content_id`、可选 `target_job_id`，返回原文块、可用优化、匹配建议及能力差距。 |
| `POST /resume-versions` | 还需 `request_id`、`version_name`、`change_summary`、`block_numbers`、可选 `optimization_ids` 和 `confirmed: true`。 |
| `GET /resume-versions`、`GET /resume-versions/{id}` | 分页查本人版本或查看内容。 |
| `PATCH /resume-versions/{id}` | 填写确认、段落与修改原因，从此系列最新版生成新快照，返回 201。 |
| `POST /applications` | 提交 `job_id`、`request_id`、可选 `resume_version_id`、渠道与投递时间。未填投递时间则生成待投递。 |
| `GET /applications`、`GET /applications/{id}` | 分页查看本人记录，列表支持 `status`。详情包含岗位快照。 |
| `PATCH /applications/{id}` | 使用 `revision` 更新备注、下一步、联系人、反馈、拒绝原因等字段。 |
| `POST /applications/{id}/status`、`GET /applications/{id}/history` | 提交 `request_id`、`revision`、`status` 和可选说明。状态历史为倒序。 |
| `POST /interview-schedules`、`GET /interview-schedules`、`PATCH /interview-schedules/{id}` | 创建、列出和修改日程。提交带偏移的 `scheduled_at`、IANA `timezone`、分钟数、轮次与形式。创建需投递 ID 和请求 UUID，修改需 `revision`。 |
| `GET /job-pipeline` | 返回目标岗位、各状态列及即将到来的面试。 |
| `GET /job-analytics` | 可选 `start`、`end` 为 UTC 日期，返回统计、日趋势及分组。 |
| `POST /job-strategy/preview`、`POST /job-strategy/analyze` | 审阅匿名统计和接收方，携带原时段和 `approval` 入队，返回 202。 |
| `GET /job-strategy/reports`、`GET /job-strategy/reports/{id}` | 列出和轮询本人的策略报告，失败时返回 `error_code`。 |

从日程调用 `POST /interviews/prepare` 或 `POST /interviews/sessions` 时传 `interview_schedule_id`。解释和计数定义见 [第九阶段使用与复测](JOB_APPLICATIONS.md)。

## 第十阶段 Sprint 2

- `GET /health` 返回 API 存活状态。 `GET /ready` 同时检查 MySQL 和完整 Worker 心跳，未就绪返回 503。
- `DELETE /api/v1/users/me` 接收 `password` 和 `confirmed: true`。成功返回 202，删除数据库数据并安排清理文件。密码错误返回 403，正在运行任务时返回 409。Cookie 请求需要 CSRF 请求头。
- 响应头 `X-Request-ID` 可用于追踪失败请求。成长中心资料和作业上传 DOCX 使用 1 MiB 文件上限，文本继续沿用原有的业务上限。

## 第十阶段 Sprint 3

投递、探索、面试和学习路线支持显式来源绑定。接口字段与历史资料处理方式见 [跨模块流程](CROSS_MODULE_WORKFLOW.md)。

## 第十阶段 Sprint 5

- `GET /api/v1/job-pipeline?limit_per_status=30` 为看板返回每列首批数据、总数和是否还有下一页。省略参数时兼容旧版响应。
- 下一页调用 `GET /api/v1/applications`，传对应的 `status`、`limit`、`recent=true`、上一页最后一条的 `before_time` 和 `before_id`。分页器使用更新时间与编号的组合排序。
- 生产身份验证和账户删除使用共享限流。超限返回 429 与 `Retry-After`。限流存储不可用时，相关操作返回 503。
