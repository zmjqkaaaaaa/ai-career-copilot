# SQL 与数据库学习手册

## 模块 8 · 数据库

### 业务与场景

用户用同一 JD 复查简历后，页面要精确找到本人对该岗位要求版本生成的报告。数据库负责把账号、岗位、简历、报告和证据关联起来。

### 技术与代码路径

[Session 配置](../../backend/app/db/session.py)、[岗位模型](../../backend/app/models/job.py)、[报告定位](../../backend/app/services/career_context.py)、[面试 JOIN](../../backend/app/services/interview_report_service.py) 和 [Alembic](../../backend/alembic/env.py)。ORM 把 Python 类和 MySQL 表对应起来，`Session` 提供对象读写和事务上下文。完整 ER 图见 [数据库设计](DATABASE_DESIGN.md)。

### 核心代码与逐段解释

[源码 · career_context.py:10](../../backend/app/services/career_context.py#L10)

```python
def matching_report(db, user_id, job_id, revision, *, content_id=None, match_id=None, filter_content=False):
    stmt = select(JobMatch).where(JobMatch.user_id == user_id, JobMatch.job_id == job_id, JobMatch.revision == revision)
    if filter_content or content_id is not None:
        stmt = stmt.where(JobMatch.content_id == content_id)
    if match_id is not None:
        chosen = owned_match(db, user_id, match_id)
        if db.scalar(stmt.where(JobMatch.id == chosen.id)) is None:
            raise ApiError(422, "CAREER_CONTEXT_MISMATCH", "匹配报告与所选岗位、JD 版本或简历版本不一致")
        return chosen
    return db.scalar(stmt.order_by(JobMatch.id.desc()).limit(1))
```

`select(JobMatch)` 读取对象；`where` 要同时匹配所有传入条件。报告归属、岗位和 JD 修订先固定，再按需要加简历版本。明确传入报告 ID 却不匹配时返回错误。只在没有明确报告 ID 时，用降序和 `limit(1)` 选择符合条件的最新记录。

[源码 · interview_report_service.py:19](../../backend/app/services/interview_report_service.py#L19)

```python
    pairs = db.execute(select(InterviewQuestion, InterviewAnswer)
                       .join(InterviewAnswer, InterviewAnswer.question_id == InterviewQuestion.id)
                       .where(InterviewQuestion.session_id == session.id).order_by(InterviewQuestion.ordinal))
```

这里是一题对应其回答的内连接。无回答的题不会产生结果行。后续报告按题序聚合，未覆盖的维度和阶段需要另行说明。若产品要显示所有题及“未答”，可以在练习中改用 LEFT JOIN 并处理缺失回答。

### 输入、输出与完整流程

前端提交岗位和简历版本 → FastAPI 解析输入、注入用户与 Session → SQLAlchemy 查询并校验版本 → Python 生成结果 → 添加报告和差距对象 → 提交事务 → 返回可展示的结构。CRUD 分别对应插入记录、按归属查询、变更状态和按业务规则删除或归档。 `Session` 退出会释放资源；`flush` 让写入进入当前事务并取得生成 ID，`commit` 才让事务持久化。

### 设计原因与常见异常

主键唯一标识一行，外键约束关联记录，连接条件决定 JOIN 粒度。复合索引 `ix_job_match_owner(user_id, id)` 有利于按用户定位和排序；数据库是否使用索引要以执行计划为准。唯一键 `(job_id, fingerprint)` 约束重复输入的匹配报告。Alembic 对数据库做版本迁移，改 Python 模型后需配套检查迁移。常见异常有唯一键冲突、外键限制、死锁、连接超时和迁移不一致。

### SQL 演练

下面是为学习编写的等价查询示例。只在合成测试库执行，并将占位值替换成测试账号数据。每行含一份匹配报告和岗位名称。

```sql
SELECT m.id, m.revision, m.content_id, m.evidence_coverage, j.position_name
FROM job_matches AS m
JOIN job_positions AS j
  ON j.id = m.job_id AND j.user_id = m.user_id
WHERE m.user_id = 101 AND m.job_id = 20 AND m.revision = 2
ORDER BY m.id DESC
LIMIT 10;
```

### 面试、练习和参考答案

- [技术面试 · 数据库](CODE_INTERVIEW_QUESTIONS.md#数据库)
- [练习 M08](CODE_EXERCISES.md#m08-数据库) · [独立核对答案](CODE_EXERCISES_ANSWERS.md#m08-数据库)
