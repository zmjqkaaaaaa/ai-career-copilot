from dataclasses import dataclass
from datetime import datetime, timedelta
from hashlib import sha256
import hmac
import json
import logging
from time import time
from urllib.parse import urlsplit

from sqlalchemy import select

from app.ai.code_project_prompts import PROMPTS
from app.ai.evidence import redact_text
from app.ai.provider import Provider, model_configured, provider_fingerprint
from app.core.config import get_settings
from app.core.errors import ApiError
from app.models.code_project import CodeProject, ProjectFile, ProjectLesson, ProjectQuiz, ProjectSnapshot, ProjectTask, QuizAttempt
from app.schemas.code_project import GradeOutput, LessonOutput, QuizOutput
from app.services.codebase_parser import mask_source, parse_file, select_entries
from app.services.github_service import GitHub
from app.services.llm_monitoring_service import TaskContext, task_provider
from app.services.project_knowledge_service import architecture, citations, files_for
from app.services.resumes import utc_now

ACTIVE = ("queued", "running")
DIMENSIONS = {"overview": "项目整体理解", "stack": "技术栈理解", "structure": "文件结构理解",
              "functions": "核心函数理解", "api": "API 流程理解", "database": "数据库理解",
              "ai": "AI 模块理解", "debug": "Debug 能力", "extension": "修改和扩展能力"}
HINTS = {"overview": "", "stack": "requirements package dependency import", "structure": "import export",
         "functions": "", "api": "route handler request response api", "database": "database select sqlalchemy prisma model",
         "ai": "openai model llm prompt", "debug": "raise exception throw error", "extension": ""}
logger = logging.getLogger(__name__)


def owned_project(db, user_id, project_id, lock=False):
    stmt = select(CodeProject).where(CodeProject.user_id == user_id, CodeProject.id == project_id)
    result = db.scalar(stmt.with_for_update() if lock else stmt)
    if result is None:
        raise ApiError(404, "CODE_PROJECT_NOT_FOUND", "未找到该项目")
    return result


def snapshot_for(db, project, commit=None):
    snap = db.scalar(select(ProjectSnapshot).where(ProjectSnapshot.project_id == project.id,
                   ProjectSnapshot.commit_sha == (commit or project.active_commit)))
    if snap is None:
        raise ApiError(404, "CODE_VERSION_NOT_FOUND", "未找到该仓库版本")
    return snap


def scoped_record(db, model, snapshot_id, record_id):
    record = db.scalar(select(model).where(model.id == record_id, model.snapshot_id == snapshot_id))
    if record is None:
        raise ApiError(404, "CODE_RECORD_NOT_FOUND", "未在此版本找到该记录")
    return record


def latest(db, model, snapshot_id, limit=40):
    return list(db.scalars(select(model).where(model.snapshot_id == snapshot_id)
                          .order_by(model.id.desc()).limit(limit)))


def idle(db, project_id):
    if db.scalar(select(ProjectTask.id).where(ProjectTask.project_id == project_id,
                 ProjectTask.state.in_(ACTIVE)).limit(1).with_for_update()) is not None:
        raise ApiError(409, "CODE_PROJECT_BUSY", "项目已有任务在处理")


def task_for(db, project_id, task_id):
    result = db.scalar(select(ProjectTask).where(ProjectTask.project_id == project_id, ProjectTask.id == task_id))
    if result is None:
        raise ApiError(404, "CODE_TASK_NOT_FOUND", "未找到此任务")
    return result


def create_task(db, project, kind, payload, key, snapshot=None):
    old = db.scalar(select(ProjectTask).where(ProjectTask.project_id == project.id, ProjectTask.request_key == key))
    if old:
        return old
    idle(db, project.id)
    task = ProjectTask(project_id=project.id, snapshot_id=snapshot.id if snapshot else None,
                       kind=kind, payload=payload, request_key=key)
    db.add(task)
    db.flush()
    return task


def study_payload(db, snapshot, body):
    if body.kind == "grade":
        if not body.quiz_id or not body.answer:
            raise ApiError(422, "CODE_ANSWER_REQUIRED", "请填写本题答案")
        quiz = scoped_record(db, ProjectQuiz, snapshot.id, body.quiz_id)
        return {"quiz_id": quiz.id, "answer": redact_text(mask_source(body.answer)), "quiz": quiz.data}
    if body.kind == "explain" and body.file_id is None:
        raise ApiError(422, "CODE_FILE_REQUIRED", "请先选择一个代码文件")
    if body.kind == "chat" and not body.question:
        raise ApiError(422, "CODE_QUESTION_REQUIRED", "请填写想了解的问题")
    if body.kind == "quiz" and not body.dimension:
        raise ApiError(422, "CODE_DIMENSION_REQUIRED", "请选择要练习的能力维度")
    files = files_for(db, snapshot.id, loaded=True)
    question = redact_text(mask_source(body.question)) if body.question else None
    history = []
    if body.kind == "chat":
        rows = [row for row in latest(db, ProjectLesson, snapshot.id, 16) if row.kind == "chat"][:3]
        history = [row.data["question"] for row in reversed(rows)]
    search = question or HINTS.get(body.dimension, "")
    evidence = citations(files, search, body.file_id, body.symbol)
    if not evidence and history and body.file_id is None:
        evidence = citations(files, " ".join(history))
    if not evidence:
        raise ApiError(422, "CODE_EVIDENCE_MISSING", "当前版本没找到相关代码，请先读取文件或改用具体路径与函数名")
    return {"commit": snapshot.commit_sha, "question": question, "previous_questions": history, "file_id": body.file_id,
            "evidence": evidence, "symbol": body.symbol, "dimension": body.dimension, "mode": body.mode}


def signature(user_id, project_id, snapshot_id, body, payload, settings, expires):
    encoded = json.dumps([user_id, project_id, snapshot_id, body.model_dump(exclude={"approval"}),
                          provider_fingerprint(settings), PROMPTS[body.kind].version, expires, payload],
                         ensure_ascii=False, sort_keys=True)
    return hmac.new(settings.jwt_secret.get_secret_value().encode(), encoded.encode(), sha256).hexdigest()


def prepare(db, project, snapshot, body, settings, expires=None):
    if not model_configured(settings):
        raise ApiError(503, "LLM_NOT_CONFIGURED", "请先配置模型服务")
    payload = study_payload(db, snapshot, body)
    expires = int(time()) + 600 if expires is None else expires
    digest = signature(project.user_id, project.id, snapshot.id, body, payload, settings, expires)
    shown = payload if body.kind != "grade" else {
        "answer": payload["answer"], "question": payload["quiz"]["question"],
        "evidence": payload["quiz"]["evidence"], "assessment_context": "还会发送系统保存的答案与评分规则",
    }
    return f"{expires}.{digest}", payload, shown


def enqueue_study(db, project, snapshot, body, settings):
    request_material = body.model_dump()
    key = sha256(json.dumps([request_material, provider_fingerprint(settings), PROMPTS[body.kind].version],
                            ensure_ascii=False, sort_keys=True).encode()).hexdigest()
    old = db.scalar(select(ProjectTask).where(ProjectTask.project_id == project.id, ProjectTask.request_key == key))
    if old:
        return old
    try:
        expires = int(body.approval.split(".", 1)[0])
    except ValueError:
        expires = 0
    if expires < time() or expires > time() + 600:
        raise ApiError(409, "CODE_PREVIEW_EXPIRED", "预览已过期，请重新核对")
    approval, payload, _ = prepare(db, project, snapshot, body, settings, expires)
    if not hmac.compare_digest(approval, body.approval):
        raise ApiError(409, "CODE_PREVIEW_CHANGED", "内容已更新，请重新核对")
    return create_task(db, project, body.kind, {"input": payload, "provider": provider_fingerprint(settings),
                       "prompt": PROMPTS[body.kind].version, "expires": expires, "approval": approval,
                       "request": body.model_dump(exclude={"approval"})}, key, snapshot)


@dataclass(frozen=True)
class Work:
    id: int
    project_id: int
    snapshot_id: int | None
    kind: str
    attempt: int
    payload: dict
    slug: str
    user_id: int
    created_at: datetime | None = None
    started_at: datetime | None = None


def collect_repository(factory, work, github):
    meta, sha, tree = github.head(work.slug)
    with factory() as db:
        existing = db.scalar(select(ProjectSnapshot.id).where(ProjectSnapshot.project_id == work.project_id,
                             ProjectSnapshot.commit_sha == sha))
    if existing:
        return {"metadata": meta, "sha": sha, "existing": existing}
    files = select_entries(github.tree(work.slug, tree))
    chosen = [file for file in files if file["metadata_json"]["priority"] <= 4
              and file["metadata_json"]["readable"]][:10]
    for item in chosen:
        try:
            raw = github.text(work.slug, item["blob_sha"], item["size"])
        except ApiError as error:
            if error.code != "GITHUB_FILE_UNREADABLE":
                raise
            item["metadata_json"]["readable"] = False
            continue
        content, index = parse_file(item["path"], item["metadata_json"]["language"], raw)
        item.update(content=content, index_data=index)
    return {"metadata": meta, "sha": sha, "files": files, "tree_sha": tree}


def collect_file(factory, work, github):
    with factory() as db:
        item = scoped_record(db, ProjectFile, work.snapshot_id, work.payload["file_id"])
    raw = github.text(work.slug, item.blob_sha, item.size)
    return parse_file(item.path, item.metadata_json["language"], raw)


def model_result(work, settings, provider_factory, factory):
    from app.schemas.code_project import StudyRequest

    saved = work.payload
    request = StudyRequest.model_validate(saved["request"])
    if saved["provider"] != provider_fingerprint(settings) or saved["prompt"] != PROMPTS[work.kind].version:
        raise ApiError(409, "MODEL_CONFIG_CHANGED", "模型或提示词已更新，请重新预览")
    expected = signature(work.user_id, work.project_id, work.snapshot_id, request, saved["input"], settings, saved["expires"])
    if not hmac.compare_digest(saved["approval"], f"{saved['expires']}.{expected}"):
        raise ApiError(409, "CODE_PREVIEW_CHANGED", "待处理内容与确认预览不一致")
    payload = saved["input"]
    provider = task_provider(provider_factory, settings, factory,
                             TaskContext("code_analysis", work.user_id, work.id, work.attempt, work.created_at, work.started_at))
    try:
        if work.kind == "grade":
            return grade(provider.generate(PROMPTS["grade"], payload, GradeOutput), payload)
        if work.kind == "quiz":
            draft = provider.generate(PROMPTS["quiz"], payload, QuizOutput)
            evidence = [item for item in payload["evidence"] if item["id"] in draft.references]
            if not evidence:
                raise ApiError(502, "CODE_QUIZ_UNGROUNDED", "题目缺少可核对的代码证据")
            quiz = draft.model_dump(exclude={"references"})
            return {**quiz, "dimension": payload["dimension"], "mode": payload["mode"], "evidence": evidence}
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
    finally:
        provider.close()


def grade(output, payload):
    rubric = payload["quiz"]["rubric"]
    returned = {item.index: item for item in output.criteria if item.index <= len(rubric)}
    points = {"correct": 1, "partial": 0.5, "missing": 0, "incorrect": 0}
    criteria = []
    for index, item in enumerate(rubric, 1):
        checked = returned.get(index)
        criteria.append({**item, "result": checked.result if checked else "missing",
                         "feedback": checked.feedback if checked else "回答未覆盖该评分点"})
    score = round(100 * sum(points[item["result"]] for item in criteria) / len(criteria))
    return {"quiz_id": payload["quiz_id"], "answer": payload["answer"], "criteria": criteria, "score": score,
            "explanation": output.explanation, "practice": output.practice, "dimension": payload["quiz"]["dimension"],
            "expected_answer": payload["quiz"]["expected_answer"]}


def complete(factory, work, result=None, error=None):
    with factory.begin() as db:
        project = db.get(CodeProject, work.project_id, with_for_update=True)
        task = db.get(ProjectTask, work.id, with_for_update=True)
        if not project or not task or task.state != "running" or task.attempt != work.attempt:
            return
        task.state = "failed" if error else "succeeded"
        task.error_code = error.code if error else None
        if error:
            if error.code == "GITHUB_RATE_LIMIT" and error.headers:
                retry_at = (int(time()) + int(error.headers["Retry-After"]) if "Retry-After" in error.headers
                            else int(error.headers.get("X-RateLimit-Reset", "0")))
                task.payload = {**task.payload, "retry_at": retry_at or None}
            return
        if work.kind == "import":
            project.active_commit = result["sha"]
            project.metadata_json = result["metadata"]
            if result.get("existing"):
                task.result_id = result["existing"]
                return
            item = ProjectSnapshot(project_id=project.id, commit_sha=result["sha"],
                                   data={"tree_sha": result["tree_sha"], "repository": result["metadata"]})
            db.add(item)
            db.flush()
            db.add_all(ProjectFile(snapshot_id=item.id, **file) for file in result["files"])
        elif work.kind == "load":
            item = scoped_record(db, ProjectFile, work.snapshot_id, work.payload["file_id"])
            item.content, item.index_data = result
        elif work.kind == "quiz":
            item = ProjectQuiz(snapshot_id=work.snapshot_id, data=result)
            db.add(item)
        elif work.kind == "grade":
            item = QuizAttempt(snapshot_id=work.snapshot_id, quiz_id=result["quiz_id"], data=result)
            db.add(item)
        else:
            item = ProjectLesson(snapshot_id=work.snapshot_id, kind=work.kind, data=result)
            db.add(item)
        db.flush()
        task.result_id = item.id


def run_code_project_once(factory, provider_factory=Provider, github_factory=GitHub):
    with factory.begin() as db:
        cutoff = utc_now() - timedelta(minutes=10)
        interrupted = db.scalars(select(ProjectTask).where(ProjectTask.state == "running",
                                 ProjectTask.started_at < cutoff).limit(30).with_for_update(skip_locked=True))
        for stale in interrupted:
            stale.state, stale.error_code = "failed", "CODE_TASK_INTERRUPTED"
        task = db.scalar(select(ProjectTask).where(ProjectTask.state == "queued").order_by(ProjectTask.id)
                         .limit(1).with_for_update(skip_locked=True))
        if task is None:
            return False
        project = db.get(CodeProject, task.project_id)
        task.state, task.started_at = "running", utc_now()
        work = Work(task.id, task.project_id, task.snapshot_id, task.kind, task.attempt, task.payload,
                    project.slug, project.user_id, task.created_at, task.started_at)
    try:
        if work.kind in {"import", "load"}:
            github = github_factory()
            try:
                result = collect_repository(factory, work, github) if work.kind == "import" else collect_file(factory, work, github)
            finally:
                github.close()
        else:
            result = model_result(work, get_settings(), provider_factory, factory)
        complete(factory, work, result)
    except ApiError as error:
        logger.info("code project task id=%s status=%s", work.id, error.code)
        complete(factory, work, error=error)
    except Exception as error:
        logger.error("code project task id=%s failed (%s)", work.id, type(error).__name__)
        complete(factory, work, error=ApiError(500, "CODE_PROJECT_TASK_FAILED", "项目任务处理失败"))
    return True


def architecture_view(db, snapshot):
    read = files_for(db, snapshot.id, loaded=True)
    paths = list(db.scalars(select(ProjectFile.path).where(ProjectFile.snapshot_id == snapshot.id)))
    lesson = db.scalar(select(ProjectLesson).where(ProjectLesson.snapshot_id == snapshot.id,
                       ProjectLesson.kind == "analyze").order_by(ProjectLesson.id.desc()).limit(1))
    return {**architecture(read, paths), "analysis": lesson.data if lesson else None}


def mastery(db, snapshot):
    attempts = latest(db, QuizAttempt, snapshot.id, 200)
    reports = [item for item in latest(db, ProjectLesson, snapshot.id, 100) if item.kind == "self_report"]
    dimensions = []
    for key, name in DIMENSIONS.items():
        scores = [item.data["score"] for item in attempts if item.data["dimension"] == key]
        note = next((item.data["note"] for item in reports if item.data["dimension"] == key), None)
        status = ("untested" if not scores else "practiced" if key == "extension"
                  else "verified_in_quiz" if max(scores) >= 75 else "needs_practice")
        practice = next((item.data["practice"] for item in attempts if item.data["dimension"] == key), None)
        dimensions.append({"key": key, "label": name, "status": status, "best_score": max(scores) if scores else None,
                           "attempts": len(scores), "self_report": note, "inferred": "当前答题证据有限" if scores else None,
                           "practice": practice or f"选择一个含相关代码的文件，完成「{name}」练习"})
    return {"commit": snapshot.commit_sha, "dimensions": dimensions,
            "attempts": [{"id": item.id, "created_at": item.created_at, **item.data} for item in attempts[:40]]}
