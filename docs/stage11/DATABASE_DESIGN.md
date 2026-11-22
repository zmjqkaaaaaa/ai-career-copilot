# AI Career Copilot 数据库设计

阶段 11.4 · 2026 年 11 月 22 日

以下收录 SQLAlchemy 的 57 张应用表。以 MySQL 方言显示字段类型，用 Alembic 离线升级 SQL 的建表清单交叉核对。数据库另维护迁移工具的 `alembic_version`，该表不属于应用模型。迁移头为 `20261121_0012`。线上实际迁移状态需在对应环境查询。

依据 [SQLAlchemy Models](../../backend/app/models)、[Alembic 迁移](../../backend/alembic/versions)、[当前迁移环境](../../backend/alembic/env.py) 和 [跨模块工作流](../CROSS_MODULE_WORKFLOW.md)。

## 阅读说明

- ER 图展示主键、外键和基数。其他分图引用的表以表名节点出现。清单列出各表完整字段、MySQL 类型、可空性、外键、唯一键和显式 ORM 索引。未标问号的字段为 NOT NULL。索引列按定义顺序列出。MySQL 为满足外键而建立的隐式索引依部署环境查询。
- 一对一由外键唯一性约束，例如一个账号最多有一份档案。普通外键形成一对多，例如一份简历有多版内容。ER 中父端为可选表示子表外键允许为空。
- `job_matches` 把多份简历版本与多个岗位关联，并保存评分和证据。它是有业务意义的关联实体，可形成业务上的多对多。岗位版本号、会话来源及部分报告引用保存在字段或 JSON 快照中，不能据此推导新的数据库外键。
- SQLAlchemy metadata 对应代码声明；部署库中的索引、外键与历史数据迁移，需要在已授权的独立环境通过 `alembic check`、`SHOW INDEX` 或 `SHOW CREATE TABLE` 验证。

## 跨表的数据流转

1. 用户上传简历，文件系统保留原件。简历内容含解析块、结构化事实和确认版本。职业画像、能力证据和优化记录围绕选定版本建立。
2. JD 保留原文和修订号，要求按版本存放。匹配报告引用岗位、简历版本和可选画像，差距条目引用该报告。可选的 AI 求职建议单独执行。
3. 投递用简历版本保存定向文本。投递记录保持当时的匹配报告、JD 快照和投递进度。探索可以从报告或投递开始，推荐可关联一个公开仓库，仓库的代码证据按提交存档。
4. 面试会话将关联资料和阶段配置固化为快照，答题反馈进入报告。学习路线保留面试报告等来源，阶段测评把结果写为学习掌握历史。驾驶舱汇总多个表的状态。

### 关键字段对照

| 字段 | 业务含义 |
| --- | --- |
| `resumes.storage_key`、`resume_contents.confirmed` | 前者定位私有原件，后者标明结构化内容是否由用户确认。 |
| `job_requirements.revision`、`ordinal` | 按 JD 修订编号和该版本内的序号定位岗位要求。 |
| `job_matches.content_id`、`revision`、`evidence_coverage` | 固定所比较的简历内容和岗位要求修订，同时记录能给出判断的证据覆盖。 |
| `job_applications.snapshot`、`valid_submission` | 固化投递使用的资料快照，并区分哪些投递可用于有效投递统计。 |
| `interview_sessions.context`、`interview_questions.parent_id` | 保存已选资料来源与相关上下文；追问可关联上一级题目。 |
| `learning_paths.data`、`learning_mastery_history.assessment_id` | 路线 JSON 保留计划与来源；掌握事件可回查到对应测评。 |
| 任务表的 `state`、`attempt`、`error_code` | 按模块保存队列状态、执行次数及失败码，可追溯某次处理，相关表的具体列见下方清单。 |

## 账户与职业画像

```mermaid
erDiagram
    users {
        integer id PK
    }
    user_profiles {
        integer id PK
        integer user_id FK
    }
    career_analyses {
        integer id PK
        integer user_id FK
        integer content_id FK
    }
    skill_profiles {
        integer id PK
        integer analysis_id FK
    }
    skill_evidence {
        integer id PK
        integer skill_profile_id FK
    }
    resume_optimization_records {
        integer id PK
        integer content_id FK
    }
    users ||..o| user_profiles : user_id
    resume_contents ||..o{ career_analyses : content_id
    users ||..o{ career_analyses : user_id
    career_analyses ||..o{ skill_profiles : analysis_id
    skill_profiles ||..o{ skill_evidence : skill_profile_id
    resume_contents ||..o{ resume_optimization_records : content_id
```

| 表及用途 | 字段与类型 | 外键 | 唯一键（主键除外） | ORM 索引 |
| --- | --- | --- | --- | --- |
| `users`<br>账号、邮箱和口令摘要；作为用户归属根 | `id INTEGER PK`<br>`email VARCHAR(254) COLLATE utf8mb4_bin`<br>`username VARCHAR(64)`<br>`password_hash VARCHAR(255)`<br>`is_active BOOL`<br>`created_at DATETIME(6)`<br>`updated_at DATETIME(6)` | — | `(email)` | — |
| `user_profiles`<br>用户自行维护的教育背景、求职目标、技能与经历 | `id INTEGER PK`<br>`user_id INTEGER`<br>`real_name VARCHAR(100)?`<br>`undergraduate_school VARCHAR(150)?`<br>`undergraduate_major VARCHAR(150)?`<br>`undergraduate_degree VARCHAR(80)?`<br>`graduate_school VARCHAR(150)?`<br>`graduate_major VARCHAR(150)?`<br>`graduation_year INTEGER?`<br>`target_position VARCHAR(150)?`<br>`interested_industries JSON`<br>`skills JSON`<br>`internship_experience JSON`<br>`project_experience JSON`<br>`created_at DATETIME(6)`<br>`updated_at DATETIME(6)` | `user_id` → `users(id)`（CASCADE） | `(user_id)` | — |
| `career_analyses`<br>面向一个目标方向及指定简历版本的画像报告 | `id INTEGER PK`<br>`user_id INTEGER`<br>`content_id INTEGER`<br>`target_direction VARCHAR(150)`<br>`analysis_result JSON`<br>`model_name VARCHAR(150)`<br>`prompt_version VARCHAR(32)`<br>`created_at DATETIME(6)` | `content_id` → `resume_contents(id)`（CASCADE）<br>`user_id` → `users(id)`（RESTRICT） | — | `ix_career_analyses_owner_created(user_id, created_at)` |
| `skill_profiles`<br>报告下的能力维度和证据状态 | `id INTEGER PK`<br>`analysis_id INTEGER`<br>`skill_name VARCHAR(80)`<br>`skill_category VARCHAR(24)`<br>`proficiency_level VARCHAR(24)`<br>`evidence_status VARCHAR(24)`<br>`analysis_reason TEXT` | `analysis_id` → `career_analyses(id)`（CASCADE） | `(analysis_id, skill_name)` | — |
| `skill_evidence`<br>能力条目可回查的原文依据 | `id INTEGER PK`<br>`skill_profile_id INTEGER`<br>`source_type VARCHAR(32)`<br>`block_number INTEGER`<br>`source_content TEXT` | `skill_profile_id` → `skill_profiles(id)`（CASCADE） | — | `ix_skill_evidence_skill_profile_id(skill_profile_id)` |
| `resume_optimization_records`<br>简历改写建议与用户确认稿 | `id INTEGER PK`<br>`content_id INTEGER`<br>`original_content TEXT`<br>`optimized_content TEXT`<br>`optimization_reason TEXT`<br>`interview_question TEXT`<br>`section VARCHAR(24)`<br>`needs_evidence BOOL`<br>`block_number INTEGER`<br>`confirmed_text TEXT?`<br>`confirmed_at DATETIME(6)?`<br>`created_at DATETIME(6)` | `content_id` → `resume_contents(id)`（CASCADE） | — | `ix_resume_optimization_records_content_id(content_id)` |

## 简历与岗位匹配

```mermaid
erDiagram
    resumes {
        integer id PK
        integer user_id FK
    }
    resume_contents {
        integer id PK
        integer resume_id FK
    }
    resume_jobs {
        integer id PK
        integer resume_id FK
    }
    job_positions {
        integer id PK
        integer user_id FK
    }
    job_requirements {
        integer id PK
        integer job_id FK
    }
    job_matches {
        integer id PK
        integer user_id FK
        integer job_id FK
        integer content_id FK
        integer analysis_id FK
    }
    job_skill_gaps {
        integer id PK
        integer match_id FK
    }
    job_analysis_tasks {
        integer id PK
        integer job_id FK
        integer match_id FK
    }
    users ||..o{ resumes : user_id
    resumes ||..o{ resume_contents : resume_id
    resumes ||..o{ resume_jobs : resume_id
    users ||..o{ job_positions : user_id
    job_positions ||..o{ job_requirements : job_id
    career_analyses |o..o{ job_matches : analysis_id
    resume_contents ||..o{ job_matches : content_id
    job_positions ||..o{ job_matches : job_id
    users ||..o{ job_matches : user_id
    job_matches ||..o{ job_skill_gaps : match_id
    job_positions ||..o{ job_analysis_tasks : job_id
    job_matches |o..o{ job_analysis_tasks : match_id
```

| 表及用途 | 字段与类型 | 外键 | 唯一键（主键除外） | ORM 索引 |
| --- | --- | --- | --- | --- |
| `resumes`<br>私有文件元数据和解析状态 | `id INTEGER PK`<br>`user_id INTEGER`<br>`original_filename VARCHAR(255)`<br>`storage_key VARCHAR(64)`<br>`file_type VARCHAR(4)`<br>`file_size INTEGER`<br>`parse_status VARCHAR(24)`<br>`parse_error VARCHAR(64)?`<br>`created_at DATETIME(6)`<br>`updated_at DATETIME(6)` | `user_id` → `users(id)`（RESTRICT） | `(storage_key)` | `ix_resumes_user_created(user_id, created_at)` |
| `resume_contents`<br>解析文本、结构化事实与经确认的内容版本 | `id INTEGER PK`<br>`resume_id INTEGER`<br>`version INTEGER`<br>`parser_version VARCHAR(32)`<br>`extracted_text MEDIUMTEXT`<br>`blocks JSON`<br>`model_blocks JSON?`<br>`structured_data JSON?`<br>`metadata_json JSON?`<br>`confirmed BOOL`<br>`created_at DATETIME(6)` | `resume_id` → `resumes(id)`（CASCADE） | `(resume_id, version)` | — |
| `resume_jobs`<br>本地解析、结构化提取、画像及优化任务 | `id INTEGER PK`<br>`resume_id INTEGER`<br>`kind VARCHAR(16)`<br>`dedupe_key VARCHAR(64)`<br>`state VARCHAR(16)`<br>`attempt INTEGER`<br>`payload JSON`<br>`result_id INTEGER?`<br>`error_code VARCHAR(64)?`<br>`created_at DATETIME(6)`<br>`started_at DATETIME(6)?`<br>`scheduled_at DATETIME(6)`<br>`finished_at DATETIME(6)?` | `resume_id` → `resumes(id)`（CASCADE） | `(resume_id, kind, dedupe_key)` | `ix_resume_jobs_queue(state, id)` |
| `job_positions`<br>目标岗位、JD 原文和修订状态 | `id INTEGER PK`<br>`user_id INTEGER`<br>`position_name VARCHAR(150)`<br>`company_name VARCHAR(150)?`<br>`location VARCHAR(150)?`<br>`job_type VARCHAR(32)?`<br>`salary_range VARCHAR(100)?`<br>`source_url VARCHAR(1000)?`<br>`job_description TEXT`<br>`parsed JSON?`<br>`revision INTEGER`<br>`confirmed BOOL`<br>`favorite BOOL`<br>`archived BOOL`<br>`discovery_metadata JSON?`<br>`created_at DATETIME`<br>`updated_at DATETIME` | `user_id` → `users(id)`（CASCADE） | — | `ix_job_owner_id(user_id, id)` |
| `job_requirements`<br>各 JD 修订下逐项岗位要求 | `id INTEGER PK`<br>`job_id INTEGER`<br>`revision INTEGER`<br>`ordinal INTEGER`<br>`requirement JSON`<br>`created_at DATETIME` | `job_id` → `job_positions(id)`（CASCADE） | `(job_id, revision, ordinal)` | — |
| `job_matches`<br>选定岗位修订及简历内容的匹配报告 | `id INTEGER PK`<br>`user_id INTEGER`<br>`job_id INTEGER`<br>`content_id INTEGER`<br>`analysis_id INTEGER?`<br>`revision INTEGER`<br>`scoring_version VARCHAR(40)`<br>`fingerprint VARCHAR(64)`<br>`overall_score FLOAT?`<br>`evidence_coverage FLOAT?`<br>`score_details JSON`<br>`recommendations JSON?`<br>`created_at DATETIME` | `analysis_id` → `career_analyses(id)`（SET NULL）<br>`content_id` → `resume_contents(id)`（CASCADE）<br>`job_id` → `job_positions(id)`（CASCADE）<br>`user_id` → `users(id)`（CASCADE） | `(job_id, fingerprint)` | `ix_job_match_owner(user_id, id)`<br>`ix_job_matches_content_id(content_id)` |
| `job_skill_gaps`<br>报告内差距、优先级与行动依据 | `id INTEGER PK`<br>`match_id INTEGER`<br>`result JSON` | `match_id` → `job_matches(id)`（CASCADE） | — | `ix_job_skill_gaps_match_id(match_id)` |
| `job_analysis_tasks`<br>JD 解析和可选求职建议任务 | `id INTEGER PK`<br>`job_id INTEGER`<br>`match_id INTEGER?`<br>`kind VARCHAR(24)`<br>`fingerprint VARCHAR(64)`<br>`payload JSON`<br>`state VARCHAR(16)`<br>`attempt INTEGER`<br>`started_at DATETIME?`<br>`error_code VARCHAR(64)?`<br>`created_at DATETIME` | `job_id` → `job_positions(id)`（CASCADE）<br>`match_id` → `job_matches(id)`（CASCADE） | `(job_id, kind, fingerprint)` | `ix_job_analysis_queue(state, id)` |

## 探索、项目与代码理解

```mermaid
erDiagram
    discovery_sessions {
        integer job_match_id FK
        integer application_id FK
        integer id PK
        integer user_id FK
    }
    discovery_messages {
        integer session_id FK
        integer id PK
        integer user_id FK
    }
    interest_records {
        integer session_id FK
        integer id PK
        integer user_id FK
    }
    pain_points {
        integer session_id FK
        integer id PK
        integer user_id FK
    }
    market_research_runs {
        integer pain_point_id FK
        integer session_id FK
        integer id PK
        integer user_id FK
    }
    competitor_records {
        integer research_id FK
        integer id PK
        integer user_id FK
    }
    opportunity_analyses {
        integer pain_point_id FK
        integer research_id FK
        integer session_id FK
        integer id PK
        integer user_id FK
    }
    project_recommendations {
        integer opportunity_id FK
        integer session_id FK
        integer id PK
        integer user_id FK
    }
    product_prds {
        integer recommendation_id FK
        integer id PK
        integer user_id FK
    }
    discovery_tasks {
        integer session_id FK
        integer id PK
        integer user_id FK
    }
    github_repositories {
        integer user_id FK
        integer recommendation_id FK
        integer id PK
    }
    project_snapshots {
        integer project_id FK
        integer id PK
    }
    project_files {
        integer snapshot_id FK
        integer id PK
    }
    project_lessons {
        integer snapshot_id FK
        integer id PK
    }
    code_quizzes {
        integer snapshot_id FK
        integer id PK
    }
    quiz_attempts {
        integer quiz_id FK
        integer snapshot_id FK
        integer id PK
    }
    code_project_tasks {
        integer project_id FK
        integer snapshot_id FK
        integer id PK
    }
    job_applications |o..o{ discovery_sessions : application_id
    job_matches |o..o{ discovery_sessions : job_match_id
    users ||..o{ discovery_sessions : user_id
    discovery_sessions ||..o{ discovery_messages : session_id
    users ||..o{ discovery_messages : user_id
    discovery_sessions ||..o{ interest_records : session_id
    users ||..o{ interest_records : user_id
    discovery_sessions ||..o{ pain_points : session_id
    users ||..o{ pain_points : user_id
    pain_points ||..o{ market_research_runs : pain_point_id
    discovery_sessions ||..o{ market_research_runs : session_id
    users ||..o{ market_research_runs : user_id
    market_research_runs ||..o{ competitor_records : research_id
    users ||..o{ competitor_records : user_id
    pain_points ||..o{ opportunity_analyses : pain_point_id
    market_research_runs |o..o{ opportunity_analyses : research_id
    discovery_sessions ||..o{ opportunity_analyses : session_id
    users ||..o{ opportunity_analyses : user_id
    opportunity_analyses ||..o{ project_recommendations : opportunity_id
    discovery_sessions ||..o{ project_recommendations : session_id
    users ||..o{ project_recommendations : user_id
    project_recommendations ||..o{ product_prds : recommendation_id
    users ||..o{ product_prds : user_id
    discovery_sessions ||..o{ discovery_tasks : session_id
    users ||..o{ discovery_tasks : user_id
    project_recommendations |o..o{ github_repositories : recommendation_id
    users ||..o{ github_repositories : user_id
    github_repositories ||..o{ project_snapshots : project_id
    project_snapshots ||..o{ project_files : snapshot_id
    project_snapshots ||..o{ project_lessons : snapshot_id
    project_snapshots ||..o{ code_quizzes : snapshot_id
    code_quizzes ||..o{ quiz_attempts : quiz_id
    project_snapshots ||..o{ quiz_attempts : snapshot_id
    github_repositories ||..o{ code_project_tasks : project_id
    project_snapshots |o..o{ code_project_tasks : snapshot_id
```

| 表及用途 | 字段与类型 | 外键 | 唯一键（主键除外） | ORM 索引 |
| --- | --- | --- | --- | --- |
| `discovery_sessions`<br>探索会话、约束和岗位或投递来源快照 | `job_match_id INTEGER?`<br>`application_id INTEGER?`<br>`source_snapshot JSON?`<br>`title VARCHAR(150)`<br>`mode VARCHAR(16)`<br>`direction VARCHAR(180)?`<br>`weekly_hours INTEGER?`<br>`updated_at DATETIME`<br>`id INTEGER PK`<br>`user_id INTEGER`<br>`created_at DATETIME` | `application_id` → `job_applications(id)`（SET NULL）<br>`job_match_id` → `job_matches(id)`（SET NULL）<br>`user_id` → `users(id)`（CASCADE） | — | `ix_discovery_sessions_application_id(application_id)`<br>`ix_discovery_sessions_job_match_id(job_match_id)`<br>`ix_discovery_sessions_user_id(user_id)` |
| `discovery_messages`<br>探索会话消息 | `role VARCHAR(16)`<br>`content TEXT`<br>`details JSON?`<br>`session_id INTEGER`<br>`id INTEGER PK`<br>`user_id INTEGER`<br>`created_at DATETIME` | `session_id` → `discovery_sessions(id)`（CASCADE）<br>`user_id` → `users(id)`（CASCADE） | — | `ix_discovery_messages_session_id(session_id)`<br>`ix_discovery_messages_user_id(user_id)` |
| `interest_records`<br>结构化兴趣与用户修订 | `data JSON`<br>`session_id INTEGER`<br>`id INTEGER PK`<br>`user_id INTEGER`<br>`created_at DATETIME` | `session_id` → `discovery_sessions(id)`（CASCADE）<br>`user_id` → `users(id)`（CASCADE） | — | `ix_interest_records_session_id(session_id)`<br>`ix_interest_records_user_id(user_id)` |
| `pain_points`<br>可核对证据的候选及已确认痛点 | `data JSON`<br>`revision INTEGER`<br>`session_id INTEGER`<br>`id INTEGER PK`<br>`user_id INTEGER`<br>`created_at DATETIME` | `session_id` → `discovery_sessions(id)`（CASCADE）<br>`user_id` → `users(id)`（CASCADE） | — | `ix_pain_points_session_id(session_id)`<br>`ix_pain_points_user_id(user_id)` |
| `market_research_runs`<br>检索材料和研究结果 | `pain_point_id INTEGER`<br>`data JSON`<br>`session_id INTEGER`<br>`id INTEGER PK`<br>`user_id INTEGER`<br>`created_at DATETIME` | `pain_point_id` → `pain_points(id)`（CASCADE）<br>`session_id` → `discovery_sessions(id)`（CASCADE）<br>`user_id` → `users(id)`（CASCADE） | — | `ix_market_research_runs_pain_point_id(pain_point_id)`<br>`ix_market_research_runs_session_id(session_id)`<br>`ix_market_research_runs_user_id(user_id)` |
| `competitor_records`<br>某轮研究的竞品证据及可编辑记录 | `research_id INTEGER`<br>`data JSON`<br>`id INTEGER PK`<br>`user_id INTEGER`<br>`created_at DATETIME` | `research_id` → `market_research_runs(id)`（CASCADE）<br>`user_id` → `users(id)`（CASCADE） | — | `ix_competitor_records_research_id(research_id)`<br>`ix_competitor_records_user_id(user_id)` |
| `opportunity_analyses`<br>围绕痛点的机会分析与评分 | `pain_point_id INTEGER`<br>`research_id INTEGER?`<br>`data JSON`<br>`session_id INTEGER`<br>`id INTEGER PK`<br>`user_id INTEGER`<br>`created_at DATETIME` | `pain_point_id` → `pain_points(id)`（CASCADE）<br>`research_id` → `market_research_runs(id)`（SET NULL）<br>`session_id` → `discovery_sessions(id)`（CASCADE）<br>`user_id` → `users(id)`（CASCADE） | — | `ix_opportunity_analyses_pain_point_id(pain_point_id)`<br>`ix_opportunity_analyses_session_id(session_id)`<br>`ix_opportunity_analyses_user_id(user_id)` |
| `project_recommendations`<br>候选方案、约束和选择状态 | `opportunity_id INTEGER`<br>`batch_id INTEGER`<br>`data JSON`<br>`favorite BOOL`<br>`selected BOOL`<br>`session_id INTEGER`<br>`id INTEGER PK`<br>`user_id INTEGER`<br>`created_at DATETIME` | `opportunity_id` → `opportunity_analyses(id)`（CASCADE）<br>`session_id` → `discovery_sessions(id)`（CASCADE）<br>`user_id` → `users(id)`（CASCADE） | — | `ix_project_recommendations_opportunity_id(opportunity_id)`<br>`ix_project_recommendations_session_id(session_id)`<br>`ix_project_recommendations_user_id(user_id)` |
| `product_prds`<br>推荐方案下逐版保存的 PRD | `recommendation_id INTEGER`<br>`version INTEGER`<br>`title VARCHAR(200)`<br>`content TEXT`<br>`origin VARCHAR(16)`<br>`based_on INTEGER?`<br>`id INTEGER PK`<br>`user_id INTEGER`<br>`created_at DATETIME` | `recommendation_id` → `project_recommendations(id)`（CASCADE）<br>`user_id` → `users(id)`（CASCADE） | `(recommendation_id, version)` | `ix_product_prds_user_id(user_id)` |
| `discovery_tasks`<br>会话中的外部研究和生成任务 | `request_key VARCHAR(64)`<br>`kind VARCHAR(24)`<br>`payload JSON`<br>`provider VARCHAR(64)`<br>`state VARCHAR(16)`<br>`attempt INTEGER`<br>`started_at DATETIME?`<br>`error_code VARCHAR(64)?`<br>`result_id INTEGER?`<br>`session_id INTEGER`<br>`id INTEGER PK`<br>`user_id INTEGER`<br>`created_at DATETIME` | `session_id` → `discovery_sessions(id)`（CASCADE）<br>`user_id` → `users(id)`（CASCADE） | `(session_id, request_key)` | `ix_discovery_queue(state, id)`<br>`ix_discovery_tasks_session_id(session_id)`<br>`ix_discovery_tasks_user_id(user_id)` |
| `github_repositories`<br>归属用户的公开仓库与可选方案绑定 | `user_id INTEGER`<br>`recommendation_id INTEGER?`<br>`slug VARCHAR(140)`<br>`metadata_json JSON`<br>`active_commit VARCHAR(64)?`<br>`id INTEGER PK`<br>`created_at DATETIME` | `recommendation_id` → `project_recommendations(id)`（SET NULL）<br>`user_id` → `users(id)`（CASCADE） | `(user_id, slug)` | `ix_github_repositories_recommendation_id(recommendation_id)`<br>`ix_github_repositories_user_id(user_id)` |
| `project_snapshots`<br>以 Git 提交 SHA 固定的仓库快照 | `project_id INTEGER`<br>`commit_sha VARCHAR(64)`<br>`data JSON`<br>`id INTEGER PK`<br>`created_at DATETIME` | `project_id` → `github_repositories(id)`（CASCADE） | `(project_id, commit_sha)` | `ix_project_snapshots_project_id(project_id)` |
| `project_files`<br>快照所含文件、代码或文件元数据 | `path VARCHAR(600) COLLATE utf8mb4_bin`<br>`blob_sha VARCHAR(64)`<br>`size INTEGER`<br>`metadata_json JSON`<br>`content MEDIUMTEXT?`<br>`index_data JSON?`<br>`snapshot_id INTEGER`<br>`id INTEGER PK`<br>`created_at DATETIME` | `snapshot_id` → `project_snapshots(id)`（CASCADE） | `(snapshot_id, path)` | `ix_project_files_snapshot_id(snapshot_id)` |
| `project_lessons`<br>代码讲解、问答或记录 | `kind VARCHAR(24)`<br>`data JSON`<br>`snapshot_id INTEGER`<br>`id INTEGER PK`<br>`created_at DATETIME` | `snapshot_id` → `project_snapshots(id)`（CASCADE） | — | `ix_project_lessons_snapshot_id(snapshot_id)` |
| `code_quizzes`<br>按代码快照保存的理解测试 | `data JSON`<br>`snapshot_id INTEGER`<br>`id INTEGER PK`<br>`created_at DATETIME` | `snapshot_id` → `project_snapshots(id)`（CASCADE） | — | `ix_code_quizzes_snapshot_id(snapshot_id)` |
| `quiz_attempts`<br>用户答题、结果及代码证据 | `quiz_id INTEGER`<br>`data JSON`<br>`snapshot_id INTEGER`<br>`id INTEGER PK`<br>`created_at DATETIME` | `quiz_id` → `code_quizzes(id)`（CASCADE）<br>`snapshot_id` → `project_snapshots(id)`（CASCADE） | — | `ix_quiz_attempts_quiz_id(quiz_id)`<br>`ix_quiz_attempts_snapshot_id(snapshot_id)` |
| `code_project_tasks`<br>导入、文件读取及代码导师任务 | `project_id INTEGER`<br>`snapshot_id INTEGER?`<br>`request_key VARCHAR(64)`<br>`kind VARCHAR(24)`<br>`payload JSON`<br>`state VARCHAR(16)`<br>`attempt INTEGER`<br>`started_at DATETIME?`<br>`result_id INTEGER?`<br>`error_code VARCHAR(64)?`<br>`id INTEGER PK`<br>`created_at DATETIME` | `project_id` → `github_repositories(id)`（CASCADE）<br>`snapshot_id` → `project_snapshots(id)`（CASCADE） | `(project_id, request_key)` | `ix_code_project_queue(state, id)`<br>`ix_code_project_tasks_project_id(project_id)` |

## 面试与学习

```mermaid
erDiagram
    interview_sessions {
        integer user_id FK
        integer id PK
    }
    interview_questions {
        integer parent_id FK
        integer session_id FK
        integer id PK
    }
    interview_answers {
        integer question_id FK
        integer session_id FK
        integer id PK
    }
    interview_reports {
        integer session_id FK
        integer id PK
    }
    interview_training_tasks {
        integer report_id FK
        integer id PK
    }
    interview_tasks {
        integer session_id FK
        integer id PK
    }
    learning_diagnoses {
        integer id PK
        integer user_id FK
    }
    learning_paths {
        integer id PK
        integer user_id FK
    }
    learning_tasks {
        integer id PK
        integer user_id FK
    }
    learning_sessions {
        integer id PK
        integer user_id FK
    }
    learning_messages {
        integer session_id FK
        integer id PK
        integer user_id FK
    }
    learning_resources {
        integer id PK
        integer user_id FK
    }
    learning_submissions {
        integer id PK
        integer user_id FK
    }
    learning_evaluations {
        integer submission_id FK
        integer id PK
        integer user_id FK
    }
    learning_assessments {
        integer id PK
        integer user_id FK
    }
    learning_mastery_history {
        integer assessment_id FK
        integer id PK
        integer user_id FK
    }
    learning_jobs {
        integer id PK
        integer user_id FK
    }
    users ||..o{ interview_sessions : user_id
    interview_questions |o..o{ interview_questions : parent_id
    interview_sessions ||..o{ interview_questions : session_id
    interview_questions ||..o| interview_answers : question_id
    interview_sessions ||..o{ interview_answers : session_id
    interview_sessions ||..o| interview_reports : session_id
    interview_reports ||..o{ interview_training_tasks : report_id
    interview_sessions ||..o{ interview_tasks : session_id
    users ||..o{ learning_diagnoses : user_id
    users ||..o{ learning_paths : user_id
    users ||..o{ learning_tasks : user_id
    users ||..o{ learning_sessions : user_id
    learning_sessions ||..o{ learning_messages : session_id
    users ||..o{ learning_messages : user_id
    users ||..o{ learning_resources : user_id
    users ||..o{ learning_submissions : user_id
    learning_submissions ||..o| learning_evaluations : submission_id
    users ||..o{ learning_evaluations : user_id
    users ||..o{ learning_assessments : user_id
    learning_assessments ||..o| learning_mastery_history : assessment_id
    users ||..o{ learning_mastery_history : user_id
    users ||..o{ learning_jobs : user_id
```

| 表及用途 | 字段与类型 | 外键 | 唯一键（主键除外） | ORM 索引 |
| --- | --- | --- | --- | --- |
| `interview_sessions`<br>训练配置、阶段、起止状态与来源快照 | `user_id INTEGER`<br>`request_id VARCHAR(36)`<br>`target VARCHAR(150)`<br>`settings JSON`<br>`context JSON`<br>`state VARCHAR(16)`<br>`revision INTEGER`<br>`started_at DATETIME?`<br>`deadline_at DATETIME?`<br>`finished_at DATETIME?`<br>`finish_reason VARCHAR(24)?`<br>`id INTEGER PK`<br>`created_at DATETIME` | `user_id` → `users(id)`（CASCADE） | `(user_id, request_id)` | `ix_interview_deadline(state, deadline_at)`<br>`ix_interview_owner(user_id, id)` |
| `interview_questions`<br>会话题目、顺序和可能的父题 | `ordinal INTEGER`<br>`stage VARCHAR(20)`<br>`parent_id INTEGER?`<br>`data JSON`<br>`session_id INTEGER`<br>`id INTEGER PK`<br>`created_at DATETIME` | `parent_id` → `interview_questions(id)`（CASCADE）<br>`session_id` → `interview_sessions(id)`（CASCADE） | `(session_id, ordinal)` | `ix_interview_questions_session_id(session_id)` |
| `interview_answers`<br>用户对某题的作答与评估 | `question_id INTEGER`<br>`text TEXT`<br>`data JSON`<br>`session_id INTEGER`<br>`id INTEGER PK`<br>`created_at DATETIME` | `question_id` → `interview_questions(id)`（CASCADE）<br>`session_id` → `interview_sessions(id)`（CASCADE） | `(question_id)` | `ix_interview_answers_session_id(session_id)` |
| `interview_reports`<br>已结束会话的覆盖、参考评分和建议 | `session_id INTEGER`<br>`data JSON`<br>`id INTEGER PK`<br>`created_at DATETIME` | `session_id` → `interview_sessions(id)`（CASCADE） | `(session_id)` | — |
| `interview_training_tasks`<br>报告薄弱项生成的练习记录 | `report_id INTEGER`<br>`state VARCHAR(16)`<br>`due_at DATETIME`<br>`completed_at DATETIME?`<br>`data JSON`<br>`id INTEGER PK`<br>`created_at DATETIME` | `report_id` → `interview_reports(id)`（CASCADE） | — | `ix_interview_training_tasks_report_id(report_id)` |
| `interview_tasks`<br>出题、答卷评估等后台任务 | `request_key VARCHAR(64)`<br>`kind VARCHAR(12)`<br>`state VARCHAR(16)`<br>`attempt INTEGER`<br>`revision INTEGER`<br>`payload JSON`<br>`started_at DATETIME?`<br>`error_code VARCHAR(64)?`<br>`session_id INTEGER`<br>`id INTEGER PK`<br>`created_at DATETIME` | `session_id` → `interview_sessions(id)`（CASCADE） | `(session_id, request_key)` | `ix_interview_queue(state, id)`<br>`ix_interview_tasks_session_id(session_id)` |
| `learning_diagnoses`<br>用户主动保存的学习能力诊断 | `data JSON`<br>`id INTEGER PK`<br>`user_id INTEGER`<br>`created_at DATETIME` | `user_id` → `users(id)`（CASCADE） | — | `ix_learning_diagnoses_user_id(user_id)` |
| `learning_paths`<br>基于预算、先修和证据的路线版本 | `version INTEGER`<br>`fingerprint VARCHAR(64)`<br>`data JSON`<br>`id INTEGER PK`<br>`user_id INTEGER`<br>`created_at DATETIME` | `user_id` → `users(id)`（CASCADE） | `(user_id, version)` | `ix_learning_paths_user_id(user_id)` |
| `learning_tasks`<br>学习排程及实际完成状态 | `task_key VARCHAR(120)`<br>`topic VARCHAR(40)`<br>`due VARCHAR(10)`<br>`status VARCHAR(20)`<br>`actual_minutes INTEGER`<br>`data JSON`<br>`id INTEGER PK`<br>`user_id INTEGER`<br>`created_at DATETIME` | `user_id` → `users(id)`（CASCADE） | `(user_id, task_key)` | `ix_learning_tasks_user_id(user_id)` |
| `learning_sessions`<br>按主题和教法组织的导师会话 | `topic VARCHAR(40)`<br>`mode VARCHAR(24)`<br>`summary JSON`<br>`id INTEGER PK`<br>`user_id INTEGER`<br>`created_at DATETIME` | `user_id` → `users(id)`（CASCADE） | — | `ix_learning_sessions_user_id(user_id)` |
| `learning_messages`<br>导师或用户逐轮消息 | `session_id INTEGER`<br>`role VARCHAR(12)`<br>`data JSON`<br>`id INTEGER PK`<br>`user_id INTEGER`<br>`created_at DATETIME` | `session_id` → `learning_sessions(id)`（CASCADE）<br>`user_id` → `users(id)`（CASCADE） | — | `ix_learning_messages_session_id(session_id)`<br>`ix_learning_messages_user_id(user_id)` |
| `learning_resources`<br>用户的学习材料与来源 | `topic VARCHAR(40)`<br>`data JSON`<br>`id INTEGER PK`<br>`user_id INTEGER`<br>`created_at DATETIME` | `user_id` → `users(id)`（CASCADE） | — | `ix_learning_resources_user_id(user_id)` |
| `learning_submissions`<br>按知识点保留的作业版本 | `topic VARCHAR(40)`<br>`version INTEGER`<br>`request_id VARCHAR(36)`<br>`data JSON`<br>`id INTEGER PK`<br>`user_id INTEGER`<br>`created_at DATETIME` | `user_id` → `users(id)`（CASCADE） | `(user_id, topic, version)` | `ix_learning_submissions_user_id(user_id)` |
| `learning_evaluations`<br>作业的评价记录和证据 | `submission_id INTEGER`<br>`data JSON`<br>`id INTEGER PK`<br>`user_id INTEGER`<br>`created_at DATETIME` | `submission_id` → `learning_submissions(id)`（CASCADE）<br>`user_id` → `users(id)`（CASCADE） | `(submission_id)` | `ix_learning_evaluations_user_id(user_id)` |
| `learning_assessments`<br>固定题库抽题、答卷和评估结果 | `topic VARCHAR(40)`<br>`form INTEGER`<br>`questions JSON`<br>`result JSON?`<br>`id INTEGER PK`<br>`user_id INTEGER`<br>`created_at DATETIME` | `user_id` → `users(id)`（CASCADE） | — | `ix_learning_assessments_user_id(user_id)` |
| `learning_mastery_history`<br>测评后掌握状态变化事件 | `assessment_id INTEGER`<br>`topic VARCHAR(40)`<br>`data JSON`<br>`id INTEGER PK`<br>`user_id INTEGER`<br>`created_at DATETIME` | `assessment_id` → `learning_assessments(id)`（CASCADE）<br>`user_id` → `users(id)`（CASCADE） | `(assessment_id)` | `ix_learning_mastery_history_user_id(user_id)` |
| `learning_jobs`<br>导师、路线补充和评价任务 | `request_key VARCHAR(64)`<br>`kind VARCHAR(16)`<br>`state VARCHAR(16)`<br>`attempt INTEGER`<br>`started_at DATETIME?`<br>`error VARCHAR(64)?`<br>`payload JSON`<br>`id INTEGER PK`<br>`user_id INTEGER`<br>`created_at DATETIME` | `user_id` → `users(id)`（CASCADE） | `(user_id, request_key)` | `ix_learning_jobs_queue(state, id)`<br>`ix_learning_jobs_user_id(user_id)` |

## 求职管理

```mermaid
erDiagram
    resume_versions {
        integer previous_id FK
        integer original_resume_id FK
        integer content_id FK
        integer target_job_id FK
        integer id PK
        integer user_id FK
    }
    job_applications {
        integer job_id FK
        integer resume_version_id FK
        integer id PK
        integer user_id FK
    }
    application_status_history {
        integer id PK
        integer application_id FK
    }
    interview_schedules {
        integer application_id FK
        integer id PK
        integer user_id FK
    }
    job_strategy_reports {
        integer id PK
        integer user_id FK
    }
    resume_contents |o..o{ resume_versions : content_id
    resumes |o..o{ resume_versions : original_resume_id
    resume_versions |o..o{ resume_versions : previous_id
    job_positions |o..o{ resume_versions : target_job_id
    users ||..o{ resume_versions : user_id
    job_positions ||..o{ job_applications : job_id
    resume_versions |o..o{ job_applications : resume_version_id
    users ||..o{ job_applications : user_id
    job_applications ||..o{ application_status_history : application_id
    job_applications ||..o{ interview_schedules : application_id
    users ||..o{ interview_schedules : user_id
    users ||..o{ job_strategy_reports : user_id
```

| 表及用途 | 字段与类型 | 外键 | 唯一键（主键除外） | ORM 索引 |
| --- | --- | --- | --- | --- |
| `resume_versions`<br>投递用文本版本、父版本和目标岗位绑定 | `request_id VARCHAR(36)`<br>`fingerprint VARCHAR(64)`<br>`series_id VARCHAR(36)`<br>`version_number INTEGER`<br>`previous_id INTEGER?`<br>`original_resume_id INTEGER?`<br>`content_id INTEGER?`<br>`target_job_id INTEGER?`<br>`job_revision INTEGER?`<br>`version_name VARCHAR(150)`<br>`target_position VARCHAR(150)?`<br>`content JSON`<br>`change_summary VARCHAR(1000)`<br>`id INTEGER PK`<br>`user_id INTEGER`<br>`created_at DATETIME`<br>`updated_at DATETIME` | `content_id` → `resume_contents(id)`（SET NULL）<br>`original_resume_id` → `resumes(id)`（SET NULL）<br>`previous_id` → `resume_versions(id)`（SET NULL）<br>`target_job_id` → `job_positions(id)`（SET NULL）<br>`user_id` → `users(id)`（CASCADE） | `(user_id, request_id)`<br>`(user_id, series_id, version_number)` | `ix_resume_versions_user_id(user_id)` |
| `job_applications`<br>一条投递使用的材料、匹配快照和进度 | `request_id VARCHAR(36)`<br>`fingerprint VARCHAR(64)`<br>`job_id INTEGER`<br>`resume_version_id INTEGER?`<br>`snapshot JSON`<br>`metadata_json JSON`<br>`channel VARCHAR(150)?`<br>`applied_at DATETIME?`<br>`current_status VARCHAR(24)`<br>`revision INTEGER`<br>`valid_submission BOOL`<br>`id INTEGER PK`<br>`user_id INTEGER`<br>`created_at DATETIME`<br>`updated_at DATETIME` | `job_id` → `job_positions(id)`（RESTRICT）<br>`resume_version_id` → `resume_versions(id)`（RESTRICT）<br>`user_id` → `users(id)`（CASCADE） | `(user_id, job_id)`<br>`(user_id, request_id)` | `ix_application_board(user_id, current_status, updated_at, id)`<br>`ix_application_owner_date(user_id, applied_at)`<br>`ix_job_applications_user_id(user_id)` |
| `application_status_history`<br>投递状态的历史变更 | `id INTEGER PK`<br>`application_id INTEGER`<br>`request_id VARCHAR(36)`<br>`previous_status VARCHAR(24)?`<br>`new_status VARCHAR(24)`<br>`changed_at DATETIME`<br>`notes VARCHAR(1000)?` | `application_id` → `job_applications(id)`（CASCADE） | `(application_id, request_id)` | `ix_application_history_status(application_id, new_status)` |
| `interview_schedules`<br>线下面试安排、状态和复盘记录 | `request_id VARCHAR(36)`<br>`fingerprint VARCHAR(64)`<br>`application_id INTEGER`<br>`scheduled_at DATETIME`<br>`ends_at DATETIME`<br>`timezone VARCHAR(80)`<br>`revision INTEGER`<br>`details JSON`<br>`id INTEGER PK`<br>`user_id INTEGER`<br>`created_at DATETIME`<br>`updated_at DATETIME` | `application_id` → `job_applications(id)`（CASCADE）<br>`user_id` → `users(id)`（CASCADE） | `(user_id, request_id)` | `ix_interview_schedule_owner_time(user_id, scheduled_at)`<br>`ix_interview_schedules_application_id(application_id)`<br>`ix_interview_schedules_user_id(user_id)` |
| `job_strategy_reports`<br>已确认匿名汇总的求职策略任务与报告 | `fingerprint VARCHAR(64)`<br>`statistics JSON`<br>`analysis JSON?`<br>`state VARCHAR(16)`<br>`attempt INTEGER`<br>`started_at DATETIME?`<br>`error_code VARCHAR(64)?`<br>`provider_key VARCHAR(64)`<br>`model_name VARCHAR(150)`<br>`prompt_version VARCHAR(32)`<br>`id INTEGER PK`<br>`user_id INTEGER`<br>`created_at DATETIME`<br>`updated_at DATETIME` | `user_id` → `users(id)`（CASCADE） | `(user_id, fingerprint)` | `ix_job_strategy_reports_state(state)`<br>`ix_job_strategy_reports_user_id(user_id)` |

## 运行与观测

```mermaid
erDiagram
    worker_heartbeats {
        varchar role PK
    }
    pending_file_deletions {
        varchar storage_key PK
    }
    auth_rate_windows {
        varchar fingerprint PK
        bigint window_start PK
    }
    llm_call_metrics {
        bigint id PK
        integer user_id FK
    }
    users ||..o{ llm_call_metrics : user_id
```

| 表及用途 | 字段与类型 | 外键 | 唯一键（主键除外） | ORM 索引 |
| --- | --- | --- | --- | --- |
| `worker_heartbeats`<br>完整 Worker 的就绪心跳 | `role VARCHAR(16) PK`<br>`observed_at DATETIME` | — | — | — |
| `pending_file_deletions`<br>私有文件删除后的持久化待清理工作 | `storage_key VARCHAR(32) PK`<br>`requested_at DATETIME`<br>`next_attempt_at DATETIME`<br>`attempts INTEGER` | — | — | `ix_pending_file_deletions_next_attempt_at(next_attempt_at)` |
| `auth_rate_windows`<br>认证操作的共享时间窗计数 | `fingerprint VARCHAR(64) PK`<br>`window_start BIGINT PK`<br>`expires_at BIGINT`<br>`hits INTEGER` | — | — | `ix_auth_rate_windows_expires_at(expires_at)` |
| `llm_call_metrics`<br>版本、状态、耗时、Token 与可选估算成本 | `id BIGINT PK`<br>`user_id INTEGER`<br>`module VARCHAR(32)`<br>`task_id INTEGER`<br>`attempt INTEGER`<br>`model VARCHAR(150)`<br>`operation VARCHAR(64)`<br>`prompt_version VARCHAR(64)`<br>`status VARCHAR(64)`<br>`duration_ms INTEGER`<br>`queue_wait_ms INTEGER?`<br>`input_tokens INTEGER?`<br>`output_tokens INTEGER?`<br>`estimated_cost NUMERIC(16, 8)?`<br>`currency VARCHAR(3)?`<br>`created_at DATETIME` | `user_id` → `users(id)`（CASCADE） | — | `ix_llm_metric_owner_time(user_id, created_at)`<br>`ix_llm_metric_task(module, task_id, attempt)`<br>`ix_llm_metric_time(created_at)` |

## 查询和完整性重点

- 邮箱唯一，个人档案的用户外键唯一。用户归属优先在服务层按验证后的身份过滤，数据库外键约束保存一致性。
- 同简历版本、同 JD 修订、项目 Git SHA、面试和学习记录的排序、检索或幂等，依赖表中的复合索引及唯一键。面向用户的查询不能只依赖某个业务编号。
- 面向待处理任务和投递看板的索引，实际是否命中需看目标数据量和 MySQL 的执行计划。模型只接收经流程检查的上下文，账密和存储键不得作为模型材料。
- JSON 用于有版本的数据结构、原文证据、外部结果与历史快照。JSON 内的引用由 Service 负责核对；独立外键和版本字段用于经常定位和核对的关系。
