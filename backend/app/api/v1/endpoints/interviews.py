from datetime import UTC
from fastapi import APIRouter, Query
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.api.dependencies import AppSettings, CurrentUser, Database
from app.core.errors import ApiError
from app.models.interview import InterviewAnswer, InterviewReport, InterviewSession, InterviewTask, InterviewTrainingTask
from app.schemas.interview import ApprovedTurn, InterviewCreate, InterviewSetup, TrainingUpdate, TurnInput
from app.services.interview_engine import busy, current, deadline, owned, preview, questions, submit, time_up
from app.services.interview_preparation_service import available, build_context
from app.services.interview_report_service import finish
from app.services.resumes import utc_now

router = APIRouter(prefix="/interviews", tags=["interview practice"])


def stamp(value):
    return value.replace(tzinfo=UTC) if value else None


def task_view(task):
    return {key: getattr(task, key) for key in ("id", "kind", "state", "attempt", "error_code")}


def brief(session):
    return {"id": session.id, "target": session.target, "settings": session.settings, "state": session.state,
            "created_at": stamp(session.created_at), "started_at": stamp(session.started_at),
            "finished_at": stamp(session.finished_at), "deadline": stamp(deadline(session)),
            "finish_reason": session.finish_reason, "sources": session.context["sources"]}


def question_view(row, teaching=False):
    data = row.data
    references = data["references"] if teaching else [
        {key: value for key, value in item.items() if key != "text"} for item in data["references"]
    ]
    return {"id": row.id, "ordinal": row.ordinal, "stage": row.stage, "parent_id": row.parent_id,
            "question": data["question"], "knowledge_point": data["knowledge_point"], "basis": data["basis"],
            "type": data["type"], "references": references, "hint": data["hint"] if teaching else None}


def progress_view(db, session):
    rows = questions(db, session.id)
    active = current(db, session) if session.state == "in_progress" and not time_up(session) else None
    answered = set(db.scalars(select(InterviewAnswer.question_id).where(InterviewAnswer.session_id == session.id)))
    assessed = list(dict.fromkeys(row.data["knowledge_point"] for row in rows if row.id in answered))
    planned = sum(row["questions"] for row in session.context["schedule"])
    completed = sum(row.id in answered and row.parent_id is None for row in rows)
    return {"question": question_view(active, session.settings["teaching"]) if active else None,
            "questions": [{"id": row.id, "ordinal": row.ordinal, "stage": row.stage, "question": row.data["question"],
                           "answered": row.id in answered, "followup": row.parent_id is not None} for row in rows],
            "schedule": session.context["schedule"], "answered": len(answered), "planned": planned,
            "remaining": max(0, planned - completed) if session.state != "finished" else 0, "assessed": assessed,
            "unassessed_stages": [item["stage"] for item in session.context["schedule"]
                                  if not any(row.stage == item["stage"] and row.id in answered for row in rows)],
            "time_expired": time_up(session) and session.state == "in_progress"}


def report_view(report):
    return {"id": report.id, "session_id": report.session_id, **report.data}


def training_view(task, session_id):
    return {"id": task.id, "session_id": session_id, "report_id": task.report_id, "state": task.state,
            "due_at": stamp(task.due_at), "completed_at": stamp(task.completed_at), **task.data}


@router.get("/options")
def options(user: CurrentUser, db: Database, application_id: int | None = Query(default=None, gt=0),
            interview_schedule_id: int | None = Query(default=None, gt=0)):
    return available(db, user.id, application_id, interview_schedule_id)


@router.post("/prepare")
def prepare(body: InterviewSetup, user: CurrentUser, db: Database):
    context = build_context(db, user.id, body)
    return {"target": context["target"], "sources": context["sources"], "schedule": context["schedule"],
            "source_types": sorted({row["kind"] for row in context["refs"]}),
            "has_project_code": any(row["kind"] == "code" for row in context["refs"])}


@router.post("/sessions", status_code=201)
def create(body: InterviewCreate, user: CurrentUser, db: Database):
    data = body.model_dump(exclude={"request_id"})
    if body.interview_schedule_id is None:
        data.pop("interview_schedule_id")
    if body.application_id is None:
        data.pop("application_id")
    key = str(body.request_id)
    stmt = select(InterviewSession).where(InterviewSession.user_id == user.id, InterviewSession.request_id == key)
    session = db.scalar(stmt)
    if session is None:
        context = build_context(db, user.id, body)
        session = InterviewSession(user_id=user.id, request_id=key, target=context["target"], settings=data, context=context)
        db.add(session)
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            session = db.scalar(stmt)
            if session is None:
                raise
    if session.settings != data:
        raise ApiError(409, "INTERVIEW_CREATE_CHANGED", "创建内容已变化，请重新准备")
    return brief(session)


@router.get("/sessions")
def list_sessions(user: CurrentUser, db: Database, before: int | None = Query(default=None, gt=0)):
    stmt = (select(InterviewSession, InterviewReport).outerjoin(InterviewReport)
            .where(InterviewSession.user_id == user.id).order_by(InterviewSession.id.desc()).limit(30))
    if before is not None:
        stmt = stmt.where(InterviewSession.id < before)
    return [{**brief(session), "score": report.data["score"] if report else None}
            for session, report in db.execute(stmt)]


@router.get("/sessions/{session_id}")
def detail(session_id: int, user: CurrentUser, db: Database):
    session = owned(db, user.id, session_id)
    latest = db.scalar(select(InterviewTask).where(InterviewTask.session_id == session.id).order_by(InterviewTask.id.desc()).limit(1))
    return {**brief(session), **progress_view(db, session), "task": task_view(latest) if latest else None}


@router.get("/sessions/{session_id}/progress")
def progress(session_id: int, user: CurrentUser, db: Database):
    return progress_view(db, owned(db, user.id, session_id))


@router.get("/sessions/{session_id}/current-question")
def current_question(session_id: int, user: CurrentUser, db: Database):
    session = owned(db, user.id, session_id)
    question = current(db, session) if session.state == "in_progress" and not time_up(session) else None
    return {"question": question_view(question, session.settings["teaching"]) if question else None}


@router.post("/sessions/{session_id}/preview")
def preview_turn(session_id: int, body: TurnInput, user: CurrentUser, db: Database, settings: AppSettings):
    data, _ = preview(db, owned(db, user.id, session_id), body, settings)
    return data


def queue(session_id, expected, body, user_id, db, settings):
    if body.kind != expected:
        raise ApiError(422, "INTERVIEW_KIND_MISMATCH", "操作与任务类型不匹配")
    task = submit(db, owned(db, user_id, session_id, lock=True), body, settings)
    db.commit()
    return task_view(task)


@router.post("/sessions/{session_id}/start", status_code=202)
def start(session_id: int, body: ApprovedTurn, user: CurrentUser, db: Database, settings: AppSettings):
    return queue(session_id, "start", body, user.id, db, settings)


@router.post("/sessions/{session_id}/answers", status_code=202)
def answer(session_id: int, body: ApprovedTurn, user: CurrentUser, db: Database, settings: AppSettings):
    return queue(session_id, "answer", body, user.id, db, settings)


@router.get("/sessions/{session_id}/tasks/{task_id}")
def get_task(session_id: int, task_id: int, user: CurrentUser, db: Database):
    owned(db, user.id, session_id)
    task = db.scalar(select(InterviewTask).where(InterviewTask.id == task_id, InterviewTask.session_id == session_id))
    if task is None:
        raise ApiError(404, "INTERVIEW_TASK_NOT_FOUND", "未找到任务")
    return task_view(task)


@router.post("/sessions/{session_id}/tasks/{task_id}/retry", status_code=202)
def retry(session_id: int, task_id: int, user: CurrentUser, db: Database):
    session = owned(db, user.id, session_id, lock=True)
    task = db.scalar(select(InterviewTask).where(InterviewTask.id == task_id, InterviewTask.session_id == session_id).with_for_update())
    if task is None:
        raise ApiError(404, "INTERVIEW_TASK_NOT_FOUND", "未找到任务")
    if (task.state != "failed" or task.attempt >= 3 or task.revision != session.revision or time_up(session)
            or task.error_code in {"MODEL_CONFIG_CHANGED", "INTERVIEW_PREVIEW_CHANGED"} or busy(db, session_id)):
        raise ApiError(409, "INTERVIEW_RETRY_UNAVAILABLE", "该任务无法重试，请重新核对发送内容")
    task.state, task.error_code, task.attempt = "queued", None, task.attempt + 1
    db.commit()
    return task_view(task)


@router.post("/sessions/{session_id}/finish")
def finish_session(session_id: int, user: CurrentUser, db: Database):
    session = owned(db, user.id, session_id, lock=True)
    if busy(db, session_id):
        raise ApiError(409, "INTERVIEW_BUSY", "请等待本轮处理完毕")
    report = finish(db, session, "time_limit" if time_up(session) else "user_ended")
    db.commit()
    return report_view(report)


@router.get("/sessions/{session_id}/report")
def report(session_id: int, user: CurrentUser, db: Database):
    owned(db, user.id, session_id)
    row = db.scalar(select(InterviewReport).where(InterviewReport.session_id == session_id))
    if row is None:
        raise ApiError(404, "INTERVIEW_REPORT_NOT_READY", "面试结束后可查看报告")
    return report_view(row)


@router.get("/training-plans")
def training(user: CurrentUser, db: Database):
    rows = db.execute(training_query(user.id).order_by(InterviewTrainingTask.id.desc()).limit(100))
    items = [training_view(task, session_id) for task, session_id in rows]
    return {"tasks": items, "done": sum(item["state"] == "done" for item in items), "total": len(items)}


@router.patch("/training-tasks/{task_id}")
def update_training(task_id: int, body: TrainingUpdate, user: CurrentUser, db: Database):
    row = db.execute(training_query(user.id).where(InterviewTrainingTask.id == task_id).with_for_update()).first()
    if row is None:
        raise ApiError(404, "INTERVIEW_TRAINING_NOT_FOUND", "未找到训练任务")
    task, session_id = row
    if task.state != body.state:
        task.state = body.state
        task.completed_at = utc_now() if body.state == "done" else None
    db.commit()
    return training_view(task, session_id)


def training_query(user_id):
    return (select(InterviewTrainingTask, InterviewSession.id).select_from(InterviewTrainingTask)
            .join(InterviewReport, InterviewReport.id == InterviewTrainingTask.report_id)
            .join(InterviewSession, InterviewSession.id == InterviewReport.session_id)
            .where(InterviewSession.user_id == user_id))
