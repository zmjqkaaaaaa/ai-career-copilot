# Python 后端学习手册

## 模块 1 · 用户认证

### 业务与场景

注册创建账户。登录证明请求者知道正确口令。换到私有简历或投递页面后，后端还要检查这条记录属于谁。没有密码登录权限的 API 也不能靠猜编号读取资料。

### 技术与代码路径

从 [AuthPage.tsx](../../frontend/src/pages/AuthPage.tsx) 和 [auth.ts](../../frontend/src/services/auth.ts) 进入 [认证路由](../../backend/app/api/v1/endpoints/auth.py)、[权限依赖](../../backend/app/api/dependencies.py)、[安全工具](../../backend/app/core/security.py) 与 [用户模型](../../backend/app/models/user.py)。技术点包括 Argon2 哈希、JWT 签名与验证、Cookie、依赖注入和用户归属。

### 核心代码与逐段解释

[源码 · auth_service.py:10](../../backend/app/services/auth_service.py#L10)

```python
def register(db: Session, data: RegisterRequest) -> User:
    email = data.email.casefold()
    if len(email) > 254:
        raise ApiError(422, "VALIDATION_ERROR", "邮箱长度不能超过 254 个字符")
    user = User(email=email, username=data.username, password_hash=password_hasher.hash(data.password))
    db.add(user)
    try:
        db.flush()
        db.refresh(user)
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        if exc.orig.args[0] == 1062:
            raise ApiError(409, "EMAIL_EXISTS", "该邮箱已注册") from None
        raise
    return user
```

邮箱规范化降低大小写重复。数据库唯一约束才是并发注册时的最后守门。哈希把口令转为验证用摘要。flush 可触发数据库写入和约束检查，commit 才提交，异常后 rollback 让会话退出失败事务。

[源码 · security.py:13](../../backend/app/core/security.py#L13)

```python
def issue_token(user_id: int, audience: str, settings: Settings) -> str:
    now = datetime.now(UTC)
    return jwt.encode(
        {"sub": str(user_id), "iss": issuer, "aud": audience, "iat": now,
         "exp": now + timedelta(minutes=settings.jwt_minutes)},
        settings.jwt_secret.get_secret_value(),
        algorithm="HS256",
    )

def token_user_id(token: str, audience: str, settings: Settings) -> int:
    payload = jwt.decode(
        token, settings.jwt_secret.get_secret_value(), algorithms=["HS256"],
        audience=audience, issuer=issuer, options={"require": ["sub", "iat", "exp"]},
    )
    subject = payload["sub"]
    if not subject.isascii() or not subject.isdecimal() or len(subject) > 10 or not 0 < int(subject) <= 2147483647:
        raise jwt.InvalidTokenError("Invalid user ID")
    return int(subject)
```

JWT 含用户主体、签发者、应用场景和过期时间。HS256 签名保护完整性，载荷仍可被解码。验证同时要求 issuer、audience 和 exp 等字段；浏览器 Cookie 与 API Bearer 使用不同 audience。登录失败时服务用通用提示；无账户时仍验证 dummy hash，以减小明显的耗时差异。

### 输入、输出与完整流程

注册输入 JSON 邮箱、用户名和口令，输出公开用户信息。网页登录使用表单字段，邮箱放入 `username`；会话接口设置 HttpOnly Cookie。浏览器刷新调用 `GET /api/v1/users/me`，鉴权依赖验证签名和当前账户可用性；读取业务对象时业务查询追加用户归属条件。API 客户端可通过独立登录端点取得 Bearer Token。

### 设计原因与常见异常

浏览器写操作校验来源和请求头，Cookie 同站策略与此配合。不能把认证结果直接等同于业务对象权限。常见异常为 409 重复邮箱、401 凭据错误或 Token 失效、403 浏览器来源检查失败、429 达到限流。任何修改身份来源的练习都应同时测匿名、本人及另一用户。

### 面试、练习和参考答案

- [技术面试 · 认证](CODE_INTERVIEW_QUESTIONS.md#认证)
- [练习 M01](CODE_EXERCISES.md#m01-用户认证) · [独立核对答案](CODE_EXERCISES_ANSWERS.md#m01-用户认证)

## 模块 6 · GitHub 项目理解

### 业务与场景

用于已经做出项目、需要讲清结构和代码的用户。用户给公开仓库地址，系统以一个提交固定资料，再从其中选出可引用的代码。

### 技术与代码路径

[ProjectWorkspacePage.tsx](../../frontend/src/pages/ProjectWorkspacePage.tsx) → [codeProjects.ts](../../frontend/src/services/codeProjects.ts) → [项目 API](../../backend/app/api/v1/endpoints/code_projects.py) → [GitHub 客户端](../../backend/app/services/github_service.py)、[文件索引](../../backend/app/services/codebase_parser.py)、[项目工作流](../../backend/app/services/code_project_workflow.py) 和 [项目模型](../../backend/app/models/code_project.py)。涉及 HTTPS REST、Git SHA、静态分析、关键词检索和引文校验。

### 核心代码与逐段解释

[源码 · project_knowledge_service.py:81](../../backend/app/services/project_knowledge_service.py#L81)

```python
                name_path = f"{file.path} {name or ''}".lower()
                score = sum(12 * (word in name_path) + 2 * (word in code.lower()) for word in words)
                if words and not score and file_id is None:
                    continue
                score += (4 if name else 0) + max(0, 5 - file.metadata_json["priority"])
                candidates.append((score, file.id, first, last, file.path, name, code))
    if symbol and not candidates:
        raise ApiError(422, "CODE_SYMBOL_UNAVAILABLE", "当前索引中没有可用的该符号片段")
    output, seen, used = [], set(), 0
    for _, file_id, first, last, path, name, code in sorted(candidates, key=lambda row: (-row[0], row[1], row[2])):
        key = (file_id, first, last)
        if key in seen or used + len(code) > CONTEXT_LIMIT:
            continue
        seen.add(key)
        used += len(code)
```

第一段用路径或符号命中的词项给较高权重，也计算代码内容命中；第二段按分数、文件和行号排序，去重后受上下文上限约束。代码远长于模型输入预算时，先缩小范围能保住关键证据。路径和行号来自选定快照。

[源码 · code_project_workflow.py:224](../../backend/app/services/code_project_workflow.py#L224)

```python
        output = provider.generate(PROMPTS[work.kind], payload, LessonOutput)
        evidence = {item["id"]: item for item in payload["evidence"]}
        sections = []
        for claim in output.sections:
            refs = [ref for ref in dict.fromkeys(claim.references) if ref in evidence]
            if claim.status in {"observed", "inferred"} and not refs:
                continue
            sections.append({**claim.model_dump(), "references": refs})
        return {**output.model_dump(), "sections": sections, "question": payload["question"], "file_id": payload.get("file_id"),
                "symbol": payload["symbol"],
                "evidence": [evidence[ref] for ref in sorted({ref for section in sections for ref in section["references"]})]}
```

模型生成讲解后，领域代码去重并核对引用编号。标成观察或推断却没有有效引用的段落会被丢弃。返回片段取自实际输入证据，仍需人工核对讲解结论是否由片段支持。

### 输入、输出与完整流程

输入公开 GitHub URL，可选推荐方案编号。路由创建导入任务 → Worker 读取仓库、提交、文件树和受限文本 → 保存快照，索引符号和架构线索 → 用户按 Git SHA 选择文件或提出问题 → 预览证据并确认发送 → Worker 调模型 → 保存讲解或失败原因，页面展示引用或测验。

### 设计原因与常见异常

固定提交可重看旧报告。该检索按词项和符号，实用且容易复核，语义同义词的召回有限。该流程读取和分析源码；运行方式不能从依赖文件单独推出。常见异常为仓库非公开、GitHub 限流、文件超限、符号无法定位或模型引用不合规。

### 面试、练习和参考答案

- [技术面试 · 仓库理解](CODE_INTERVIEW_QUESTIONS.md#仓库理解)
- [练习 M06](CODE_EXERCISES.md#m06-github-项目理解) · [独立核对答案](CODE_EXERCISES_ANSWERS.md#m06-github-项目理解)

## 模块 7 · 模拟面试

### 业务与场景

用户有简历、JD 或项目资料，想练习针对性追问。面试过程含设置、作答、下一题、结束和报告，退出或刷新后依赖保存的数据恢复。

### 技术与代码路径

[InterviewPracticePage.tsx](../../frontend/src/pages/InterviewPracticePage.tsx) → [面试 API](../../backend/app/api/v1/endpoints/interviews.py) → [来源准备](../../backend/app/services/interview_preparation_service.py)、[会话引擎](../../backend/app/services/interview_engine.py)、[评分校验](../../backend/app/services/interview_evaluation_service.py)、[报告](../../backend/app/services/interview_report_service.py)、[面试模型](../../backend/app/models/interview.py)。涉及状态机、多轮上下文、任务与报告事务。

### 核心代码与逐段解释

[源码 · interview_engine.py:262](../../backend/app/services/interview_engine.py#L262)

```python
        can_follow = (len(rows) < 18 and has_time and session.settings["deep_followup"] and question.parent_id is None
                      and result.action in {"follow_up", "probe_error"} and result.followup_reason
                      and excerpt(result.followup_quote, payload["answer"]))
        if can_follow and add_question(db, session, question.stage, result.next_question, payload["sources"], rows,
                                       question, result.followup_reason, result.followup_quote):
            session.revision += 1
            return
        stage = next_stage(session, rows, question, result.action)
        if not stage:
            finish(db, session, "planned_complete")
            return
        draft = result.next_question if result.action == "advance" and stage == payload["next_stage"] else None
        next_sources = payload["sources"] if draft else choose_sources(session, stage)
        add_question(db, session, stage, draft, next_sources, rows)
        session.revision += 1
```

模型建议追问或推进。代码检查总题量、阶段时间、用户选项、当前题是否已经属于追问、追问理由与回答片段。满足条件后才能写入子题并提升修订号，其他情况进入阶段推进或结束。持久化会话维护连续性，不要求模型自己维护跨请求状态。

[源码 · interview_report_service.py:36](../../backend/app/services/interview_report_service.py#L36)

```python
    def summary(rows):
        coverage = average([row["coverage"] for row in rows])
        weighted = [(row["score"], row["coverage"]) for row in rows
                    if row["score"] is not None and row["coverage"] >= 50]
        total = sum(weight for _, weight in weighted)
        score = round(sum(value * weight for value, weight in weighted) / total, 2) if total and coverage >= 50 else None
        return {"score": score, "coverage": coverage, "answered": len(rows)}
```

聚合先计算覆盖，再按有效覆盖加权。覆盖不足时分数可以为空。报告关联答题引用、不同阶段与未评估范围，后续可据薄弱项继续复练。

### 输入、输出与完整流程

输入目标、阶段、时长及可选资料。准备页核对归属和来源 → 创建会话和快照 → 用户授权出题或当前轮作答 → 入队 → Worker 给模型所需材料 → 领域规则核对评价和追问 → 写已答内容和下一题，或结束保存报告及练习。模型任务路径失败时页面可提示该轮失败，版本变化要求按流程重新确认。

### 设计原因与常见异常

回合修订和任务尝试号防止较旧输出覆盖新状态。相同会话报告可复用，未回答的阶段保持未评估。常见异常包括材料缺失、确认过期、重复回答、到期、引文不出自原回答、模型超时。

### 面试、练习和参考答案

- [技术面试 · 模拟面试](CODE_INTERVIEW_QUESTIONS.md#模拟面试)
- [练习 M07](CODE_EXERCISES.md#m07-模拟面试) · [独立核对答案](CODE_EXERCISES_ANSWERS.md#m07-模拟面试)
