import ast
from datetime import timedelta
from hashlib import sha256
import hmac
import json
import logging
from pathlib import Path
from time import time
from urllib.parse import urlsplit

from sqlalchemy import select

from app.ai.learning_prompts import EVALUATION, LESSON, PATH
from app.ai.provider import Provider, model_configured, provider_fingerprint
from app.core.config import get_settings
from app.core.errors import ApiError
from app.models.learning import LearningEvaluation, LearningJob, LearningMessage, LearningPath, LearningSession, LearningSubmission, LearningTask
from app.models.user import User
from app.schemas.learning import EvaluationOutput, LessonOutput
from app.services.interview_evaluation_service import excerpt
from app.services.interview_preparation_service import clean
from app.services.learning_catalog import FIXTURES, MODES, PROJECT_EXAMPLES, TOPICS
from app.services.resumes import utc_now

PROMPTS = {"lesson": LESSON, "evaluation": EVALUATION, "path": PATH}
ACTIVE = ("queued", "running")
logger = logging.getLogger(__name__)
RUBRICS = {
    "code": ["功能正确性", "代码结构", "异常处理", "可读性", "测试完整性"],
    "analysis": ["用户理解", "需求分析", "逻辑结构", "竞品研究", "产品方案", "证据质量"],
    "prd": ["用户理解", "需求与范围", "核心流程", "验收", "证据质量"],
    "github": ["实现说明", "证据质量", "边界和测试"],
    "text": ["概念准确性", "应用过程", "验收或证据"],
    "markdown": ["概念准确性", "应用过程", "验收或证据"],
}
AI_RUBRIC = ["模型调用", "提示词设计", "结构化输出", "异常处理", "效果评估"]


def own(db, model, user, identifier, lock=False):
    query = select(model).where(model.id == identifier, model.user_id == user)
    item = db.scalar(query.with_for_update() if lock else query)
    if item is None:
        raise ApiError(404, "LEARNING_NOT_FOUND", "没有找到这条学习记录")
    return item


def lock_user(db, user):
    db.scalar(select(User.id).where(User.id == user).with_for_update())


def topic_for(key):
    if key not in TOPICS:
        raise ApiError(404, "LEARNING_TOPIC_UNKNOWN", "没有找到该知识点")
    return TOPICS[key]


def rubric(kind, topic):
    if topic in {"prompt", "rag", "agent", "project"} and kind in {"text", "code", "markdown"}:
        return AI_RUBRIC
    return RUBRICS[kind]


def static_check(kind, topic, text):
    if kind != "code":
        return {"status": "not_applicable", "detail": "按提交内容评估"}
    if topic == "sql":
        return {"status": "not_run", "detail": "按 SQL 文本检查思路，数据库未执行"}
    try:
        tree = ast.parse(text)
        return {"status": "parsed", "detail": "Python 语法可解析",
                "functions": sum(isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) for node in ast.walk(tree))}
    except (SyntaxError, ValueError, RecursionError):
        return {"status": "syntax_error", "detail": "未通过 Python 语法解析"}


def evidence_review(result, material):
    proposed = {item.criterion: item for item in result.ratings}
    rows = []
    for criterion in material["rubric"]:
        item = proposed.get(criterion)
        level = item.level if item and excerpt(item.quote, material["content"]) else None
        if material["static"]["status"] == "syntax_error" and criterion == "功能正确性":
            rows.append({"criterion": criterion, "level": 0, "quote": None, "reason": "Python 语法检查未通过"})
        else:
            rows.append({"criterion": criterion, "level": level, "quote": item.quote if level is not None else None,
                         "reason": item.reason if level is not None else "缺少可引用的提交证据"})
    scores = [row["level"] for row in rows if row["level"] is not None]
    coverage = round(100 * len(scores) / len(rows))
    score = round(25 * sum(scores) / len(scores), 2) if coverage >= 50 else None
    checks_passed = all(row["passed"] for row in (material.get("fixture") or []))
    return {**result.model_dump(exclude={"ratings"}), "ratings": rows, "score": score, "coverage": coverage,
            "rubric_version": "learning-rubric-1", "prompt_version": EVALUATION.version,
            "static": material["static"], "fixture": material.get("fixture"),
            "status": "completed" if score is not None and score >= 75 and checks_passed
            and material["static"]["status"] != "syntax_error" else "needs_revision"}


def project_example(topic):
    source = PROJECT_EXAMPLES.get(topic)
    if not source:
        return None
    path, symbol = source
    try:
        text = (Path(__file__).resolve().parents[2] / path).read_text(encoding="utf-8")
        node = next((item for item in ast.walk(ast.parse(text))
                     if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)) and item.name == symbol), None)
        if node:
            end = min(node.end_lineno, node.lineno + 11)
            return {"path": path, "symbol": symbol, "line": node.lineno, "end": end,
                    "text": clean("\n".join(text.splitlines()[node.lineno - 1:end]), 2400)}
    except (OSError, SyntaxError, ValueError):
        return None


def material(db, user, body):
    if body.kind == "lesson":
        row = own(db, LearningSession, user, body.record_id)
        if not body.message:
            raise ApiError(422, "MESSAGE_REQUIRED", "请先输入本轮内容")
        return {"topic": topic_for(row.topic)["title"], "exercise": topic_for(row.topic)["exercise"],
                "mode": MODES[row.mode], "message": clean(body.message, 3000),
                "current_question": row.summary.get("question"), "summary": row.summary.get("summary"),
                "project_example": project_example(row.topic)}
    if body.kind == "path":
        row = own(db, LearningPath, user, body.record_id)
        return {"target": clean(row.data["target"]), "goal": clean(row.data["goal"]),
                "weekly_minutes": row.data["weekly_minutes"],
                "modules": [{"title": item["title"], "reason": item["reason"], "requires": item["requires"]}
                            for item in row.data["modules"]]}
    row = own(db, LearningSubmission, user, body.record_id)
    if db.scalar(select(LearningEvaluation.id).where(LearningEvaluation.submission_id == row.id)) is not None:
        raise ApiError(409, "LEARNING_EVALUATED", "这份提交已有反馈")
    content = row.data["content"]
    if not content and row.data.get("repository_url"):
        raise ApiError(422, "LEARNING_REPOSITORY_SUMMARY_REQUIRED", "请在新版本附上相关代码片段或实现说明，再申请评估")
    fixed = FIXTURES.get(row.topic)
    supplied = row.data.get("sample_outputs")
    fixture = [{"case": label, "expected": fixed["expected"][key], "observed": supplied.get(key),
                "passed": supplied.get(key) == fixed["expected"][key]}
               for key, label in fixed["labels"].items()] if fixed and supplied is not None else None
    return {"topic": topic_for(row.topic)["title"], "objective": topic_for(row.topic)["exercise"],
            "rubric": rubric(row.data["kind"], row.topic), "content": clean(content, 8500),
            "static": static_check(row.data["kind"], row.topic, content), "fixture": fixture}


def digest(settings, user, kind, record, data, expires):
    encoded = json.dumps([user, kind, record, data, expires, provider_fingerprint(settings), PROMPTS[kind].version],
                         ensure_ascii=False, sort_keys=True)
    return hmac.new(settings.jwt_secret.get_secret_value().encode(), encoded.encode(), sha256).hexdigest()


def preview(db, user, body, settings, expires=None):
    if not model_configured(settings):
        raise ApiError(503, "LLM_NOT_CONFIGURED", "请先配置模型服务")
    data = material(db, user, body)
    if len(json.dumps(data, ensure_ascii=False)) > settings.llm_max_input_chars:
        raise ApiError(422, "LEARNING_INPUT_TOO_LONG", "请缩短要发送的文本")
    expiry = int(time()) + 600 if expires is None else expires
    return {"approval": f"{expiry}.{digest(settings, user, body.kind, body.record_id, data, expiry)}",
            "payload": data, "model_host": urlsplit(settings.llm_base_url or "").hostname}


def enqueue(db, user, body, settings):
    lock_user(db, user)
    key = sha256(json.dumps(body.model_dump(), ensure_ascii=False, sort_keys=True).encode()).hexdigest()
    old = db.scalar(select(LearningJob).where(LearningJob.user_id == user, LearningJob.request_key == key))
    if old:
        return old
    if not body.approval:
        raise ApiError(422, "APPROVAL_REQUIRED", "请先核对发送预览")
    if db.scalar(select(LearningJob.id).where(LearningJob.user_id == user, LearningJob.state.in_(ACTIVE)).limit(1)):
        raise ApiError(409, "LEARNING_BUSY", "已有学习任务在处理")
    expires = int(body.approval.split(".", 1)[0])
    if expires < time() or expires > time() + 600:
        raise ApiError(409, "LEARNING_PREVIEW_EXPIRED", "预览已过期")
    checked = preview(db, user, body, settings, expires)
    if not hmac.compare_digest(checked["approval"], body.approval):
        raise ApiError(409, "LEARNING_PREVIEW_CHANGED", "内容已更新，请重新预览")
    item = LearningJob(user_id=user, kind=body.kind, request_key=key, payload={**checked, "record_id": body.record_id,
                       "provider": provider_fingerprint(settings), "prompt": PROMPTS[body.kind].version})
    db.add(item)
    db.flush()
    return item


def complete(factory, user, job_id, attempt, result=None, error=None):
    with factory.begin() as db:
        lock_user(db, user)
        job = db.get(LearningJob, job_id, with_for_update=True)
        if job.state != "running" or job.attempt != attempt:
            return
        job.state, job.error = ("failed", error) if error else ("succeeded", None)
        if error:
            return
        record_id = job.payload["record_id"]
        if job.kind == "evaluation":
            reviewed = evidence_review(result, job.payload["payload"])
            db.add(LearningEvaluation(user_id=user, submission_id=record_id,
                                      data=reviewed))
            submission = own(db, LearningSubmission, user, record_id)
            task = db.scalar(select(LearningTask).where(LearningTask.user_id == user, LearningTask.topic == submission.topic,
                             LearningTask.status == "submitted").order_by(LearningTask.id.desc()).limit(1).with_for_update())
            newest = db.scalar(select(LearningSubmission.id).where(LearningSubmission.user_id == user,
                               LearningSubmission.topic == submission.topic).order_by(LearningSubmission.id.desc()).limit(1))
            if task and newest == record_id:
                task.status = reviewed["status"]
            current_path = db.scalar(select(LearningPath).where(LearningPath.user_id == user).order_by(LearningPath.id.desc()).limit(1))
            if current_path:
                from app.services.learning_plan import make_path

                db.flush()
                make_path(db, user, current_path.data["weekly_minutes"], current_path.data["goal"], "作业反馈后复核学习优先级")
        elif job.kind == "lesson":
            session = own(db, LearningSession, user, record_id)
            output = result.model_dump()
            db.add(LearningMessage(user_id=user, session_id=session.id, role="user",
                                   data={"text": job.payload["payload"]["message"]}))
            db.add(LearningMessage(user_id=user, session_id=session.id, role="mentor",
                                   data={**output, "prompt_version": LESSON.version}))
            session.summary = {"summary": output["summary"], "question": output["question"], "next_step": output["next_step"]}
        else:
            path = own(db, LearningPath, user, record_id)
            path.data = {**path.data, "mentor": result.model_dump(), "prompt_version": PATH.version}


def run_learning_once(factory, provider_factory=Provider):
    now = utc_now()
    with factory.begin() as db:
        stale = db.scalars(select(LearningJob).where(LearningJob.state == "running",
                           LearningJob.started_at < now - timedelta(minutes=10)).limit(20).with_for_update(skip_locked=True))
        for row in stale:
            row.state, row.error = "failed", "LEARNING_INTERRUPTED"
        job = db.scalar(select(LearningJob).where(LearningJob.state == "queued").order_by(LearningJob.id)
                        .limit(1).with_for_update(skip_locked=True))
        if not job:
            return False
        job.state, job.started_at = "running", now
        job_id, user, attempt, kind, saved = job.id, job.user_id, job.attempt, job.kind, job.payload
    settings = get_settings()
    try:
        expires = int(saved["approval"].split(".", 1)[0])
        signature = digest(settings, user, kind, saved["record_id"], saved["payload"], expires)
        if saved["provider"] != provider_fingerprint(settings) or saved["prompt"] != PROMPTS[kind].version:
            raise ApiError(409, "MODEL_CONFIG_CHANGED", "请重新预览")
        if not hmac.compare_digest(saved["approval"], f"{expires}.{signature}"):
            raise ApiError(409, "LEARNING_PREVIEW_CHANGED", "请重新预览")
        provider = provider_factory(settings)
        try:
            result = provider.generate(PROMPTS[kind], saved["payload"], EvaluationOutput if kind == "evaluation" else LessonOutput)
        finally:
            provider.close()
        complete(factory, user, job_id, attempt, result)
    except ApiError as error:
        complete(factory, user, job_id, attempt, error=error.code)
    except Exception as error:
        logger.error("learning job %d failed (%s)", job_id, type(error).__name__)
        complete(factory, user, job_id, attempt, error="LEARNING_JOB_FAILED")
    return True

