# 技术题代码定位清单

每题列出真实代码、接口、相关数据契约及验证入口。测试名称用于定位，执行结果以测试记录为准。

## T01

**为什么项目选择 FastAPI？**

- 代码 [create_app](../../backend/app/main.py#L29) · [router = APIRouter](../../backend/app/api/v1/api.py#L5)
- 请求或入口 GET /health
- 数据、Prompt 或约束 运行探针，无业务表或 Prompt
- 验证 [test_health](../../backend/tests/test_api.py#L19)

## T02

**浏览器怎么请求后端？**

- 代码 [request](../../frontend/src/services/api.ts#L14) · [proxy:](../../frontend/vite.config.ts#L8)
- 请求或入口 POST /api/v1/jobs/{job_id}/match
- 数据、Prompt 或约束 JobMatch 由服务端生成，浏览器对接响应
- 验证 [test_dashboard_error_recovery_and_mobile_navigation](../../backend/tests/test_sprint6.py#L29)

## T03

**如何注册和保存密码？**

- 代码 [register](../../backend/app/services/auth_service.py#L10) · [register_user](../../backend/app/api/v1/endpoints/auth.py#L16)
- 请求或入口 POST /api/v1/auth/register
- 数据、Prompt 或约束 User，邮箱唯一及密码哈希
- 验证 [test_register_hash_and_duplicate](../../backend/tests/test_api.py#L43)

## T04

**浏览器登录后如何恢复？**

- 代码 [create_session](../../backend/app/api/v1/endpoints/auth.py#L28) · [current_user](../../backend/app/api/dependencies.py#L22)
- 请求或入口 POST /api/v1/auth/session、GET /api/v1/users/me
- 数据、Prompt 或约束 User；issue_token 与 token_user_id 使用对应 audience
- 验证 [test_cookie_session_csrf_cors_and_logout](../../backend/tests/test_api.py#L127)

## T05

**用户资料如何隔离？**

- 代码 [matching_report](../../backend/app/services/career_context.py#L10) · [current_user](../../backend/app/api/dependencies.py#L22)
- 请求或入口 GET /api/v1/job-matches/{match_id}
- 数据、Prompt 或约束 User、JobMatch 与投递来源约束
- 验证 [test_two_jobs_keep_selected_sources](../../backend/tests/test_career_context.py#L34)

## T06

**文件如何上传？**

- 代码 [store_upload](../../backend/app/services/resume_storage.py#L18) · [upload_resume](../../backend/app/api/v1/endpoints/resumes.py#L22)
- 请求或入口 POST /api/v1/resumes/upload
- 数据、Prompt 或约束 Resume 文件元数据及私有文件系统
- 验证 [test_upload_validation_and_empty_pdf](../../backend/tests/test_resumes.py#L51)

## T07

**PDF 和 DOCX 怎么转成证据？**

- 代码 [parse_resume](../../backend/app/services/resume_parser.py#L91) · [compute](../../backend/app/resume_worker.py#L59)
- 请求或入口 POST /api/v1/resumes/{resume_id}/parse
- 数据、Prompt 或约束 ResumeContent；本地解析不调用模型
- 验证 [test_parse_ten_synthetic_resumes](../../backend/tests/test_resumes.py#L41)

## T08

**后台任务如何处理？**

- 代码 [claim_job](../../backend/app/resume_worker.py#L41) · [complete](../../backend/app/resume_worker.py#L98)
- 请求或入口 GET /api/v1/resume-jobs/{job_id}
- 数据、Prompt 或约束 ResumeJob、ResumeContent；AI 任务使用对应 Prompt
- 验证 [test_two_worker_lanes_start_short_task_before_slow_finishes](../../backend/tests/test_sprint5.py#L95)

## T09

**模型如何通过 API 接入？**

- 代码 [_complete](../../backend/app/ai/provider.py#L74) · [compute](../../backend/app/resume_worker.py#L59)
- 请求或入口 POST /api/v1/resumes/{resume_id}/extract
- 数据、Prompt 或约束 ResumeJob；EXTRACT 和 StructuredResume
- 验证 [test_provider_rejects_malformed_response](../../backend/tests/test_resumes.py#L195)

## T10

**Prompt 怎么管理？**

- 代码 [PromptRegistry](../../backend/app/prompts/registry.py#L92) · [EXTRACT =](../../backend/app/ai/prompts.py#L3)
- 请求或入口 POST /api/v1/resumes/{resume_id}/extract
- 数据、Prompt 或约束 Prompt 定义、baseline.json 与 ResumeJob 输入版本
- 验证 [test_registry_detects_unversioned_edit_and_can_select_archived_revision](../../backend/tests/test_ai_evaluation.py#L28)

## T11

**模型 JSON 失败如何处理？**

- 代码 [generate](../../backend/app/ai/provider.py#L46) · [grounded_requirements](../../backend/app/services/job_parser.py#L18)
- 请求或入口 POST /api/v1/jobs/{job_id}/parse
- 数据、Prompt 或约束 JDResult、JobAnalysisTask、JD_PROMPT
- 验证 [test_provider_rejects_malformed_response](../../backend/tests/test_resumes.py#L195)

## T12

**SQLAlchemy Session 如何工作？**

- 代码 [get_db](../../backend/app/db/session.py#L19) · [create_match](../../backend/app/api/v1/endpoints/jobs.py#L136)
- 请求或入口 POST /api/v1/jobs/{job_id}/match
- 数据、Prompt 或约束 JobMatch、JobSkillGap 事务；无模型评分
- 验证 [test_job_lifecycle](../../backend/tests/test_jobs.py#L77)

## T13

**怎样设计匹配和差距数据库？**

- 代码 [JobMatch](../../backend/app/models/job.py#L37) · [JobSkillGap](../../backend/app/models/job.py#L54)
- 请求或入口 GET /api/v1/job-matches/{match_id}/gaps
- 数据、Prompt 或约束 JobMatch 的复合唯一键及差距外键
- 验证 [test_job_lifecycle](../../backend/tests/test_jobs.py#L77)

## T14

**数据库迁移如何验证？**

- 代码 [target_metadata =](../../backend/alembic/env.py#L10) · [JobPosition](../../backend/app/models/job.py#L6)
- 请求或入口 迁移命令 alembic upgrade head，无业务 API
- 数据、Prompt 或约束 Base.metadata、迁移头 20261121_0012
- 验证 [DATABASE_DESIGN.md](../../docs/stage11/DATABASE_DESIGN.md)

## T15

**JD 如何解析和确认？**

- 代码 [parse_jd](../../backend/app/services/job_parser.py#L46) · [confirm](../../backend/app/api/v1/endpoints/jobs.py#L124)
- 请求或入口 POST /api/v1/jobs/{job_id}/parse、PUT /api/v1/jobs/{job_id}/requirements
- 数据、Prompt 或约束 JD_PROMPT、JDResult、JobRequirement
- 验证 [test_job_lifecycle](../../backend/tests/test_jobs.py#L77)

## T16

**岗位分和覆盖率怎么算？**

- 代码 [score](../../backend/app/services/job_matching_service.py#L115) · [compare_requirement](../../backend/app/services/job_matching_service.py#L59)
- 请求或入口 POST /api/v1/jobs/{job_id}/match
- 数据、Prompt 或约束 JobMatch；core/job_scoring.py 的权重为规则
- 验证 [test_scoring](../../backend/tests/test_jobs.py#L22)

## T17

**两次匹配如何保持可比？**

- 代码 [create_match](../../backend/app/api/v1/endpoints/jobs.py#L136) · [matching_report](../../backend/app/services/career_context.py#L10)
- 请求或入口 POST /api/v1/jobs/{job_id}/match
- 数据、Prompt 或约束 JobMatch.revision、content_id、scoring_version
- 验证 [test_two_jobs_keep_selected_sources](../../backend/tests/test_career_context.py#L34)

## T18

**GitHub API 怎么接入？**

- 代码 [head](../../backend/app/services/github_service.py#L70) · [collect_repository](../../backend/app/services/code_project_workflow.py#L171)
- 请求或入口 POST /api/v1/code-projects/import
- 数据、Prompt 或约束 CodeProject 与 ProjectSnapshot；导入使用 GitHub REST
- 验证 [test_github_rejects_unsafe_or_limited_repository](../../backend/tests/test_code_projects.py#L214)

## T19

**代码讲解如何构造上下文？**

- 代码 [citations](../../backend/app/services/project_knowledge_service.py#L45) · [model_result](../../backend/app/services/code_project_workflow.py#L201)
- 请求或入口 POST /api/v1/code-projects/{project_id}/explain
- 数据、Prompt 或约束 ProjectFile、ProjectLesson、讲解提示与 LessonOutput
- 验证 [test_project_full_flow](../../backend/tests/test_code_projects.py#L131)

## T20

**多轮面试怎样存取？**

- 代码 [generation_input](../../backend/app/services/interview_engine.py#L99) · [complete](../../backend/app/services/interview_engine.py#L233)
- 请求或入口 POST /api/v1/interviews/sessions/{session_id}/answers
- 数据、Prompt 或约束 InterviewSession、Question、Answer、Task；面试评价 Prompt
- 验证 [test_combined_moves_across_all_stages_and_holds_source_version](../../backend/tests/test_interviews.py#L205)

## T21

**动态追问怎样挡住无关问题？**

- 代码 [can_follow =](../../backend/app/services/interview_engine.py#L262) · [next_stage](../../backend/app/services/interview_engine.py#L65)
- 请求或入口 POST /api/v1/interviews/sessions/{session_id}/answers
- 数据、Prompt 或约束 InterviewQuestion.parent_id、评价结果的 action
- 验证 [test_interview_modes](../../backend/tests/test_interviews.py#L117)

## T22

**面试分怎样生成？**

- 代码 [evaluate](../../backend/app/services/interview_evaluation_service.py#L32) · [finish](../../backend/app/services/interview_report_service.py#L11)
- 请求或入口 GET /api/v1/interviews/sessions/{session_id}/report
- 数据、Prompt 或约束 InterviewReport、EvaluationDraft 和评分规则
- 验证 [test_fixture_and_rubric_boundaries](../../backend/tests/test_interviews.py#L182)

## T23

**模型失败如何重试？**

- 代码 [start_job](../../backend/app/services/resume_jobs.py#L25) · [generate](../../backend/app/ai/provider.py#L46)
- 请求或入口 POST /api/v1/resumes/{resume_id}/extract
- 数据、Prompt 或约束 ResumeJob 失败、确认、尝试号和 Prompt 版本
- 验证 [test_model_failure_requires_explicit_retry](../../backend/tests/test_resumes.py#L178)

## T24

**怎样控制 API 成本？**

- 代码 [record](../../backend/app/services/llm_monitoring_service.py#L37) · [provider_fingerprint](../../backend/app/ai/provider.py#L28)
- 请求或入口 各模型任务接口；本地监控模块有汇总命令
- 数据、Prompt 或约束 LlmCallMetric 存模型、Prompt 版本和用量
- 验证 [test_monitor_persists_only_metadata_and_estimated_usage](../../backend/tests/test_sprint5.py#L145)

## T25

**删除账号如何处理数据库外的文件？**

- 代码 [delete_account](../../backend/app/services/account_deletion.py#L42) · [clean_file_once](../../backend/app/services/account_deletion.py#L57)
- 请求或入口 DELETE /api/v1/users/me
- 数据、Prompt 或约束 User 与 PendingFileDeletion
- 验证 [test_account_delete_with_derived_data_and_resumable_cleanup](../../backend/tests/test_operations.py#L76)
