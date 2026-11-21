from dataclasses import dataclass
from datetime import timedelta
from hashlib import sha256
import hmac
import json
import logging
import re
from time import time
from urllib.parse import urlsplit

from sqlalchemy import select

from app.ai.interview_prompts import START, TURN
from app.ai.provider import Provider, model_configured, provider_fingerprint
from app.core.config import get_settings
from app.core.errors import ApiError
from app.models.interview import InterviewAnswer, InterviewQuestion, InterviewSession, InterviewTask
from app.schemas.interview import EvaluationDraft, QuestionDraft
from app.services.interview_evaluation_service import ANCHORS, evaluate, excerpt, rules
from app.services.interview_modes import DEFAULT_QUESTIONS, QUESTION_TYPES
from app.services.interview_preparation_service import clean
from app.services.interview_report_service import finish
from app.services.resumes import utc_now

logger = logging.getLogger(__name__)
ACTIVE = ("queued", "running")
PROMPTS = {"start": START, "answer": TURN}
TERMS = re.compile(r"[A-Za-z_][A-Za-z_0-9]{1,}|[\u4e00-\u9fff]{2,}")


def owned(db, user, identifier, lock=False):
    stmt = select(InterviewSession).where(InterviewSession.id == identifier, InterviewSession.user_id == user)
    session = db.scalar(stmt.with_for_update() if lock else stmt)
    if session is None:
        raise ApiError(404, "INTERVIEW_NOT_FOUND", "未找到该场面试")
    return session


def busy(db, session_id):
    return db.scalar(select(InterviewTask).where(InterviewTask.session_id == session_id,
                     InterviewTask.state.in_(ACTIVE)).order_by(InterviewTask.id.desc()).limit(1))


def questions(db, session_id):
    return list(db.scalars(select(InterviewQuestion).where(InterviewQuestion.session_id == session_id)
                           .order_by(InterviewQuestion.ordinal)))


def current(db, session):
    return db.scalar(select(InterviewQuestion).outerjoin(InterviewAnswer, InterviewAnswer.question_id == InterviewQuestion.id)
                     .where(InterviewQuestion.session_id == session.id, InterviewAnswer.id.is_(None))
                     .order_by(InterviewQuestion.ordinal.desc()).limit(1))


def deadline(session):
    return session.deadline_at


def time_up(session):
    end = deadline(session)
    return bool(end and utc_now() >= end)


def next_stage(session, rows, question, action="advance"):
    if len(rows) >= 18:
        return None
    current_stage = question.stage
    schedule = session.context["schedule"]
    spec = next(value for value in schedule if value["stage"] == current_stage)
    stage_rows = [item for item in rows if item.stage == current_stage]
    timed = spec["minutes"] and (utc_now() - stage_rows[0].created_at).total_seconds() >= spec["minutes"] * 60
    if (action != "end_stage" and not timed
            and sum(item.parent_id is None for item in stage_rows) < spec["questions"]):
        return current_stage
    position = next(i for i, value in enumerate(schedule) if value["stage"] == current_stage)
    return schedule[position + 1]["stage"] if position + 1 < len(schedule) else None


def choose_sources(session, stage, answer="", required=()):
    priorities = {
        "intro": ("resume", "profile", "jd"), "resume": ("resume", "ability", "profile", "jd"),
        "project": ("code", "practice", "plan", "resume"), "product": ("jd", "plan", "gap"),
        "technical": ("jd", "code", "ability", "gap"), "scenario": ("plan", "jd", "gap"), "reverse": ("jd",),
    }[stage]
    terms = set(TERMS.findall(answer.lower()[:500]))
    pool = [row for row in session.context["refs"] if row["kind"] in priorities or row["id"] in required]
    pool.sort(key=lambda row: (row["id"] not in required, priorities.index(row["kind"]) if row["kind"] in priorities else -1,
                               -sum(word in row["text"].lower() for word in terms)))
    picked = []
    for row in pool:
        if row["id"] in required or sum(other["kind"] == row["kind"] for other in picked) < 4:
            picked.append(row)
        if len(picked) == 10:
            break
    return picked


def generation_input(db, session, body):
    options = {key: session.settings[key] for key in ("mode", "difficulty", "style", "teaching", "deep_followup")}
    if body.kind == "start":
        if session.state != "ready":
            raise ApiError(409, "INTERVIEW_ALREADY_STARTED", "该面试已开始")
        stage = session.context["schedule"][0]["stage"]
        return {**options, "target": session.target, "stage": stage, "sources": choose_sources(session, stage)}
    if session.state != "in_progress" or time_up(session):
        raise ApiError(409, "INTERVIEW_INACTIVE", "该面试已结束或时限已到")
    question = current(db, session)
    if not question or question.id != body.question_id:
        raise ApiError(409, "INTERVIEW_QUESTION_CHANGED", "当前问题已更新，请刷新")
    rows = questions(db, session.id)
    answer = clean(body.answer, 3500)
    if not answer.strip():
        raise ApiError(422, "INTERVIEW_ANSWER_REQUIRED", "请输入有效答案")
    stage = question.stage
    following = next_stage(session, rows, question)
    sources = choose_sources(session, stage, answer, [item["id"] for item in question.data["references"]])
    if following and following != stage:
        for row in choose_sources(session, following, answer)[:3]:
            if row["id"] not in {item["id"] for item in sources}:
                sources.append(row)
    return {
        **options, "target": session.target, "stage": stage, "next_stage": following,
        "current_question": question.data["question"], "knowledge_point": question.data["knowledge_point"],
        "question_references": [item["id"] for item in question.data["references"]],
        "answer": answer, "rubric": rules(question.data["type"]), "anchors": ANCHORS, "sources": sources,
        "recent_topics": [item.data["knowledge_point"] for item in rows[-4:-1]],
        "recent_questions": [item.data["question"] for item in rows[-5:]],
    }


def signing(settings, user, sid, revision, kind, payload, expires):
    material = json.dumps([user, sid, revision, kind, provider_fingerprint(settings),
                           PROMPTS[kind].version, expires, payload], ensure_ascii=False, sort_keys=True)
    return hmac.new(settings.jwt_secret.get_secret_value().encode(), material.encode(), sha256).hexdigest()


def preview(db, session, body, settings, expires=None):
    if not model_configured(settings):
        raise ApiError(503, "LLM_NOT_CONFIGURED", "请先配置模型服务")
    payload = generation_input(db, session, body)
    if len(json.dumps(payload, ensure_ascii=False)) > settings.llm_max_input_chars:
        payload["recent_topics"] = []
        payload["recent_questions"] = []
        while len(payload["sources"]) > 1 and len(json.dumps(payload, ensure_ascii=False)) > settings.llm_max_input_chars:
            payload["sources"].pop()
        if len(json.dumps(payload, ensure_ascii=False)) > settings.llm_max_input_chars:
            raise ApiError(422, "INTERVIEW_INPUT_TOO_LONG", "请缩短本次回答后再发送")
    expires = int(time()) + 600 if expires is None else expires
    digest = signing(settings, session.user_id, session.id, session.revision, body.kind, payload, expires)
    shown = {key: value for key, value in payload.items() if key not in {"anchors", "rubric"}}
    if body.kind == "answer":
        shown["evaluation_context"] = "还会发送固定的评分维度与规则"
    return {"approval": f"{expires}.{digest}", "context": shown,
            "model_host": urlsplit(settings.llm_base_url or "").hostname}, payload


def submit(db, session, body, settings):
    encoded = json.dumps(body.model_dump(), ensure_ascii=False, sort_keys=True)
    key = sha256(encoded.encode()).hexdigest()
    existing = db.scalar(select(InterviewTask).where(InterviewTask.session_id == session.id, InterviewTask.request_key == key))
    if existing:
        return existing
    if busy(db, session.id):
        raise ApiError(409, "INTERVIEW_BUSY", "已有面试任务在处理")
    expires = int(body.approval.split(".", 1)[0])
    if expires < time() or expires > time() + 600:
        raise ApiError(409, "INTERVIEW_PREVIEW_EXPIRED", "请重新核对本次发送内容")
    checked, payload = preview(db, session, body, settings, expires)
    if not hmac.compare_digest(checked["approval"], body.approval):
        raise ApiError(409, "INTERVIEW_PREVIEW_CHANGED", "资料或作答已变化，请重新核对")
    task = InterviewTask(session_id=session.id, kind=body.kind, revision=session.revision, request_key=key,
                         payload={"input": payload, "expires": expires, "approval": body.approval,
                                  "prompt": PROMPTS[body.kind].version, "provider": provider_fingerprint(settings),
                                  "question_id": body.question_id, "original_answer": body.answer})
    db.add(task)
    db.flush()
    return task


def add_question(db, session, stage, result, source_rows, rows, parent=None, reason=None, quote=None):
    mapping = {item["id"]: item for item in source_rows}
    refs = [mapping[key] for key in dict.fromkeys(result.references) if key in mapping] if result else []
    valid = result and (result.basis != "source" or bool(refs)) and (result.basis != "answer" or parent is not None)
    if result and any(re.sub(r"[\s？?。.!！]", "", row.data["question"]).casefold()
                      == re.sub(r"[\s？?。.!！]", "", result.question).casefold() for row in rows):
        valid = False
    if stage == "project" and any(item["kind"] == "code" for item in source_rows) and not parent:
        valid = valid and any(item["kind"] == "code" for item in refs)
        if not valid:
            code = [item for item in source_rows if item["kind"] == "code"]
            refs = [max(code, key=lambda item: ("." in (item.get("symbol") or ""),
                                                item["text"].lstrip().startswith(("def ", "function ")),
                                                bool(item.get("symbol"))))]
            reference = refs[0]
            fallback = (f"请结合 {reference['path']} 第 {reference['start']}–{reference['end']} 行，说明这段代码的输入与输出。",
                        "源码输入输出")
        else:
            fallback = DEFAULT_QUESTIONS[stage]
    else:
        fallback = DEFAULT_QUESTIONS[stage]
    if parent and not valid:
        return False
    text, point = (result.question, result.knowledge_point) if valid else fallback
    if not valid and any(row.data["question"] == text for row in rows):
        text = f"围绕「{point}」，请说明你会用什么证据验证自己的判断（第 {len(rows) + 1} 题）。"
    if not valid and stage == "resume" and any(item["kind"] == "resume" for item in source_rows):
        ref = next(item for item in source_rows if item["kind"] == "resume")
        refs = [ref]
        text = f"请结合简历第 {ref['block'] or 1} 段，说明你的个人职责和成果验证方法。"
    elif not valid and stage != "project":
        refs = []
    data = {"question": text, "knowledge_point": point, "type": QUESTION_TYPES[stage],
            "basis": result.basis if valid else ("source" if refs else "scenario"), "references": refs,
            "hint": result.hint if valid and session.settings["teaching"] else None,
            "followup_reason": reason, "followup_quote": quote, "prompt_version": (TURN if rows else START).version}
    db.add(InterviewQuestion(session_id=session.id, ordinal=len(rows) + 1, stage=stage, created_at=utc_now(),
                            parent_id=parent.id if parent else None, data=data))
    return True


@dataclass(frozen=True)
class Work:
    id: int
    session_id: int
    user_id: int
    kind: str
    attempt: int
    revision: int
    data: dict


def complete(factory, work, result=None, error=None):
    with factory.begin() as db:
        session = db.get(InterviewSession, work.session_id, with_for_update=True)
        task = db.get(InterviewTask, work.id, with_for_update=True)
        if not session or not task or task.state != "running" or work.attempt != task.attempt:
            return
        if error or work.revision != session.revision:
            task.state, task.error_code = "failed", error or "INTERVIEW_PREVIEW_CHANGED"
            return
        payload = work.data["input"]
        task.state = "succeeded"
        if work.kind == "start":
            session.state, session.started_at = "in_progress", utc_now()
            session.deadline_at = session.started_at + timedelta(minutes=session.settings["minutes"])
            add_question(db, session, payload["stage"], result, payload["sources"], [])
            session.revision += 1
            return
        question = current(db, session)
        assess = evaluate(question.data["type"], result, payload["answer"])
        db.add(InterviewAnswer(session_id=session.id, question_id=question.id, text=work.data["original_answer"],
                               data={**assess, "prompt_version": work.data["prompt"]}))
        db.flush()
        rows = questions(db, session.id)
        if time_up(session):
            finish(db, session, "time_limit")
            return
        position = next(p for p in session.context["schedule"] if p["stage"] == question.stage)
        stage_started = next(row.created_at for row in rows if row.stage == question.stage)
        has_time = not position["minutes"] or (utc_now() - stage_started).total_seconds() < position["minutes"] * 60
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


def run_interview_once(factory, provider_factory=Provider):
    now = utc_now()
    with factory.begin() as db:
        stale = db.scalars(select(InterviewTask).where(InterviewTask.state == "running",
                           InterviewTask.started_at < now - timedelta(minutes=10)).limit(25).with_for_update(skip_locked=True))
        for task in stale:
            task.state, task.error_code = "failed", "INTERVIEW_TASK_INTERRUPTED"
        task = db.scalar(select(InterviewTask).where(InterviewTask.state == "queued").order_by(InterviewTask.id)
                         .limit(1).with_for_update(skip_locked=True))
        if task is None:
            active = select(InterviewTask.id).where(InterviewTask.session_id == InterviewSession.id,
                                                    InterviewTask.state.in_(ACTIVE)).exists()
            expired = db.scalar(select(InterviewSession).where(InterviewSession.state == "in_progress",
                                InterviewSession.deadline_at <= now, ~active).order_by(InterviewSession.deadline_at)
                                .limit(1).with_for_update(skip_locked=True))
            if expired:
                finish(db, expired, "time_limit")
            return expired is not None
        session = db.get(InterviewSession, task.session_id)
        task.state, task.started_at = "running", now
        work = Work(task.id, session.id, session.user_id, task.kind, task.attempt, task.revision, task.payload)
    settings = get_settings()
    try:
        saved = work.data
        if saved["provider"] != provider_fingerprint(settings) or saved["prompt"] != PROMPTS[work.kind].version:
            raise ApiError(409, "MODEL_CONFIG_CHANGED", "模型配置已更新")
        digest = signing(settings, work.user_id, work.session_id, work.revision, work.kind, saved["input"], saved["expires"])
        if not hmac.compare_digest(saved["approval"], f"{saved['expires']}.{digest}"):
            raise ApiError(409, "INTERVIEW_PREVIEW_CHANGED", "内容已变化")
        provider = provider_factory(settings)
        try:
            result = provider.generate(PROMPTS[work.kind], saved["input"], QuestionDraft if work.kind == "start" else EvaluationDraft)
        finally:
            provider.close()
        complete(factory, work, result)
    except ApiError as error:
        complete(factory, work, error=error.code)
    except Exception as error:
        logger.error("interview task %s failed (%s)", work.id, type(error).__name__)
        complete(factory, work, error="INTERVIEW_TASK_FAILED")
    return True
