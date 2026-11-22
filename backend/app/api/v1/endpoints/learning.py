from datetime import date, timedelta
from io import BytesIO
from pathlib import PurePath

from fastapi import APIRouter, File, Form, UploadFile
from sqlalchemy import func, select

from app.api.dependencies import AppSettings, CurrentUser, Database
from app.core.errors import ApiError
from app.models.learning import (LearningAssessment, LearningDiagnosis, LearningEvaluation, LearningJob, LearningMastery,
    LearningMessage, LearningPath, LearningResource, LearningSession, LearningSubmission, LearningTask)
from app.schemas.learning import Answers, PlanInput, ResourceInput, ReviewInput, SessionInput, SubmissionInput, TaskEdit, TaskInput, TopicInput
from app.services.github_service import normalize_repo
from app.services.learning_assessment import exam
from app.services.learning_catalog import CATEGORIES, FIXTURES, MODES, OPEN_FORMATS, TOPICS
from app.services.learning_plan import daily, diagnosis, interview_source, interview_source_view, latest, make_path
from app.services.learning_resources import CATALOG
from app.services.learning_workflow import ACTIVE, enqueue, lock_user, own, preview, rubric, topic_for
from app.services.resume_parser import docx_sections, validate_file
from app.services.resumes import utc_now

router = APIRouter(prefix="/learning", tags=["learning mentor"])


def view(row, *keys):
    return {"id": row.id, "created_at": row.created_at, **{key: getattr(row, key) for key in keys}}


def rows(db, model, user, *conds, limit=100):
    return list(db.scalars(select(model).where(model.user_id == user, *conds).order_by(model.id.desc()).limit(limit)))


def task_view(row):
    return view(row, "topic", "due", "status", "actual_minutes", "data")


def job_view(row):
    return view(row, "kind", "state", "attempt", "error")


@router.get("/catalog")
def catalog(user: CurrentUser):
    return {"topics": list(TOPICS.values()), "categories": CATEGORIES, "modes": MODES}


@router.get("/diagnosis")
def current_diagnosis(user: CurrentUser, db: Database):
    return diagnosis(db, user.id)


@router.post("/diagnosis", status_code=201)
def save_diagnosis(user: CurrentUser, db: Database):
    lock_user(db, user.id)
    data = diagnosis(db, user.id)
    last = latest(db, LearningDiagnosis, user.id)
    if last and last.data == data:
        return view(last, "data")
    row = LearningDiagnosis(user_id=user.id, data=data)
    db.add(row)
    db.commit()
    return view(row, "data")


@router.post("/paths/generate", status_code=201)
def generate_path(body: PlanInput, user: CurrentUser, db: Database):
    lock_user(db, user.id)
    reason = "按本次面试反馈与先修生成" if body.interview_report_id else "按目标、优先级与先修生成"
    item = make_path(db, user.id, body.weekly_minutes, body.goal, reason, interview_report_id=body.interview_report_id)
    db.commit()
    return view(item, "version", "data")


@router.get("/interview-sources/{report_id}")
def read_interview_source(report_id: int, user: CurrentUser, db: Database):
    return interview_source_view(*interview_source(db, user.id, report_id))


@router.get("/paths")
def list_paths(user: CurrentUser, db: Database):
    return [view(item, "version", "data") for item in rows(db, LearningPath, user.id, limit=30)]


@router.get("/paths/{path_id}")
def read_path(path_id: int, user: CurrentUser, db: Database):
    return view(own(db, LearningPath, user.id, path_id), "version", "data")


@router.patch("/paths/{path_id}")
def update_path(path_id: int, body: PlanInput, user: CurrentUser, db: Database):
    lock_user(db, user.id)
    item = own(db, LearningPath, user.id, path_id)
    if latest(db, LearningPath, user.id).id != item.id:
        raise ApiError(409, "LEARNING_PATH_CHANGED", "请从最新版调整")
    source_id = (body.interview_report_id if "interview_report_id" in body.model_fields_set
                 else item.data.get("source", {}).get("report_id"))
    revised = make_path(db, user.id, body.weekly_minutes, body.goal, "用户调整目标或时间预算",
                        interview_report_id=source_id)
    db.commit()
    return view(revised, "version", "data")


@router.get("/tasks/daily")
def get_daily(user: CurrentUser, db: Database, day: date | None = None):
    lock_user(db, user.id)
    today = day or utc_now().date()
    daily(db, user.id, latest(db, LearningPath, user.id), today)
    items = rows(db, LearningTask, user.id, LearningTask.due == today.isoformat())
    db.commit()
    scheduled = [task_view(item) for item in items]
    return {"tasks": scheduled, "date": today.isoformat(), "minutes": sum(item["data"]["minutes"] for item in scheduled)}


@router.post("/tasks", status_code=201)
def create_task(body: TaskInput, user: CurrentUser, db: Database, day: date | None = None):
    lock_user(db, user.id)
    path = latest(db, LearningPath, user.id)
    if not path:
        raise ApiError(409, "LEARNING_PATH_REQUIRED", "请先生成学习路线")
    topic = topic_for(body.topic)
    today = day or utc_now().date()
    key = f"manual:{today.isoformat()}:{body.topic}"
    item = db.scalar(select(LearningTask).where(LearningTask.user_id == user.id, LearningTask.task_key == key))
    if item is None:
        first = (today - timedelta(days=today.weekday())).isoformat()
        last = (today + timedelta(days=6-today.weekday())).isoformat()
        planned = rows(db, LearningTask, user.id, LearningTask.due >= first, LearningTask.due <= last, limit=200)
        if sum(row.data["minutes"] for row in planned) + body.minutes > path.data["weekly_minutes"]:
            raise ApiError(422, "LEARNING_BUDGET", "任务超过本周学习时间预算")
        item = LearningTask(user_id=user.id, task_key=key, topic=body.topic, due=today.isoformat(),
                            data={**topic, "minutes": body.minutes, "type": body.task_type or topic["type"]})
        db.add(item)
        db.commit()
    return task_view(item)


@router.patch("/tasks/{task_id}")
def update_task(task_id: int, body: TaskEdit, user: CurrentUser, db: Database):
    item = own(db, LearningTask, user.id, task_id, lock=True)
    item.status = body.status
    if body.actual_minutes is not None:
        item.actual_minutes = body.actual_minutes
    db.commit()
    return task_view(item)


@router.get("/sessions")
def sessions(user: CurrentUser, db: Database):
    return [view(item, "topic", "mode", "summary") for item in rows(db, LearningSession, user.id, limit=40)]


@router.post("/sessions", status_code=201)
def create_session(body: SessionInput, user: CurrentUser, db: Database):
    topic_for(body.topic)
    if body.mode not in MODES:
        raise ApiError(422, "LEARNING_MODE", "请选择教学模式")
    row = LearningSession(user_id=user.id, topic=body.topic, mode=body.mode, summary={})
    db.add(row)
    db.commit()
    return view(row, "topic", "mode", "summary")


@router.get("/sessions/{session_id}/history")
def history(session_id: int, user: CurrentUser, db: Database, before: int | None = None):
    row = own(db, LearningSession, user.id, session_id)
    conditions = [LearningMessage.session_id == row.id]
    if before:
        conditions.append(LearningMessage.id < before)
    return {"session": view(row, "topic", "mode", "summary"),
            "messages": [view(item, "role", "data") for item in reversed(rows(db, LearningMessage, user.id, *conditions, limit=80))]}


@router.get("/resources")
def resources(user: CurrentUser, db: Database, topic: str | None = None):
    items = rows(db, LearningResource, user.id, *([LearningResource.topic == topic] if topic else []))
    return [item for item in CATALOG if not topic or item["topic"] == topic] + [
        {**view(row, "topic"), **row.data} for row in items]


def add_resource(db, user, topic, data):
    topic_for(topic)
    row = LearningResource(user_id=user, topic=topic, data=data)
    db.add(row)
    db.commit()
    return {**view(row, "topic"), **data}


@router.post("/resources", status_code=201)
def resource(body: ResourceInput, user: CurrentUser, db: Database):
    if not body.url and not body.text:
        raise ApiError(422, "LEARNING_RESOURCE_EMPTY", "请填写来源链接或笔记")
    return add_resource(db, user.id, body.topic, {**body.model_dump(mode="json", exclude={"topic"}),
                        "source": "用户保存", "credibility": "由用户核对"})


def read_text(upload, maximum):
    suffix = PurePath(upload.filename or "").suffix.lower()
    if suffix not in {".txt", ".md", ".docx"}:
        raise ApiError(415, "LEARNING_FILE_TYPE", "学习上传支持 UTF-8 文本、Markdown 和 DOCX")
    limit = 1024 * 1024 if suffix == ".docx" else maximum
    data = upload.file.read(limit + 1)
    if len(data) > limit:
        raise ApiError(413, "LEARNING_FILE_LIMIT", "文件超过当前大小限制")
    try:
        if suffix == ".docx":
            stream = BytesIO(data)
            validate_file(stream, "docx")
            parts, length = [], 0
            for _, line in docx_sections(stream):
                length += len(line) + 2
                if length > maximum:
                    raise ApiError(413, "LEARNING_FILE_LIMIT", "文档文字超出读取上限")
                parts.append(line)
            text = "\n\n".join(parts).strip()
        else:
            text = data.decode("utf-8-sig").strip()
    except UnicodeDecodeError:
        raise ApiError(422, "LEARNING_FILE_ENCODING", "文件必须是 UTF-8 文本") from None
    except ApiError:
        raise
    except Exception:
        raise ApiError(422, "LEARNING_FILE_INVALID", "无法提取文档文字") from None
    if not text or any(ord(char) < 32 and char not in "\r\n\t" for char in text):
        raise ApiError(422, "LEARNING_FILE_INVALID", "文件没有有效文字或包含控制字符")
    return text


@router.post("/resources/upload", status_code=201)
def upload_resource(user: CurrentUser, db: Database, topic: str = Form(max_length=40), title: str = Form(max_length=150),
                    file: UploadFile = File()):
    if not title.strip():
        raise ApiError(422, "LEARNING_RESOURCE_EMPTY", "请填写标题")
    return add_resource(db, user.id, topic, {"title": title.strip(), "kind": "upload", "text": read_text(file, 24000),
                        "source": "用户上传的文本", "credibility": "由用户核对"})


@router.get("/assignments")
def assignments(user: CurrentUser):
    return [{**item, "submission": "提交文本、Markdown、代码、产品分析、PRD 或 GitHub 链接",
             "fixtures": FIXTURES.get(key, {}).get("labels", {}),
             "rubrics": {kind: rubric(kind, key) for kind in ("text", "code", "analysis", "prd", "github")}}
            for key, item in TOPICS.items()]


def add_submission(db, user, topic, data, request_id):
    spec = topic_for(topic)
    lock_user(db, user)
    previous = rows(db, LearningSubmission, user, LearningSubmission.topic == topic, limit=1)
    same = db.scalar(select(LearningSubmission).where(LearningSubmission.user_id == user,
                     LearningSubmission.topic == topic, LearningSubmission.request_id == request_id))
    if same:
        if same.data != data:
            raise ApiError(409, "LEARNING_SUBMISSION_CHANGED", "重试内容与已保存版本不同")
        return view(same, "topic", "version", "data")
    item = LearningSubmission(user_id=user, topic=spec["id"], request_id=request_id, data=data,
                              version=previous[0].version + 1 if previous else 1)
    db.add(item)
    task = db.scalar(select(LearningTask).where(LearningTask.user_id == user, LearningTask.topic == topic,
                     LearningTask.status.in_(("in_progress", "needs_revision", "submitted")))
                     .order_by(LearningTask.id.desc()).limit(1).with_for_update())
    if task:
        task.status = "submitted"
    db.commit()
    return view(item, "topic", "version", "data")


@router.post("/assignments/{topic}/submit", status_code=201)
def submit_assignment(topic: str, body: SubmissionInput, user: CurrentUser, db: Database):
    url = "https://github.com/" + normalize_repo(body.repository_url) if body.repository_url else None
    if not body.content and not url:
        raise ApiError(422, "LEARNING_SUBMISSION_EMPTY", "请填写提交内容")
    if body.kind == "github" and not url:
        raise ApiError(422, "LEARNING_SUBMISSION_URL", "请输入公开 GitHub 仓库地址")
    if body.sample_outputs is not None and set(body.sample_outputs) != set(FIXTURES.get(topic, {}).get("labels", {})):
        raise ApiError(422, "LEARNING_FIXTURE_CASES", "请为每道固定样例填写结果")
    return add_submission(db, user.id, topic, {**body.model_dump(exclude={"request_id"}), "repository_url": url}, str(body.request_id))


@router.post("/assignments/{topic}/upload", status_code=201)
def submit_file(topic: str, user: CurrentUser, db: Database, request_id: str = Form(min_length=36, max_length=36),
                file: UploadFile = File()):
    return add_submission(db, user.id, topic, {"kind": "markdown", "content": read_text(file, 12000),
                          "repository_url": None}, request_id)


@router.get("/assignments/{topic}/submissions")
def submissions(topic: str, user: CurrentUser, db: Database):
    topic_for(topic)
    joined = db.execute(select(LearningSubmission, LearningEvaluation)
        .outerjoin(LearningEvaluation, LearningEvaluation.submission_id == LearningSubmission.id)
        .where(LearningSubmission.user_id == user.id, LearningSubmission.topic == topic)
        .order_by(LearningSubmission.id.desc()).limit(50))
    return [{**view(item, "topic", "version", "data"), "status": feedback.data["status"] if feedback else "submitted",
             "evaluation": feedback.data if feedback else None} for item, feedback in joined]


@router.post("/preview")
def preview_job(body: ReviewInput, user: CurrentUser, db: Database, settings: AppSettings):
    return preview(db, user.id, body, settings)


def queue(db, user, body, settings):
    job = enqueue(db, user, body, settings)
    db.commit()
    return job_view(job)


@router.post("/sessions/{session_id}/messages", status_code=202)
def message(session_id: int, body: ReviewInput, user: CurrentUser, db: Database, settings: AppSettings):
    if body.kind != "lesson" or body.record_id != session_id:
        raise ApiError(422, "LEARNING_JOB_MISMATCH", "课程与请求不一致")
    return queue(db, user.id, body, settings)


@router.post("/submissions/{submission_id}/evaluate", status_code=202)
def evaluate_submission(submission_id: int, body: ReviewInput, user: CurrentUser, db: Database, settings: AppSettings):
    if body.kind != "evaluation" or body.record_id != submission_id:
        raise ApiError(422, "LEARNING_JOB_MISMATCH", "作业与请求不一致")
    return queue(db, user.id, body, settings)


@router.post("/paths/{path_id}/coach", status_code=202)
def coach_path(path_id: int, body: ReviewInput, user: CurrentUser, db: Database, settings: AppSettings):
    if body.kind != "path" or body.record_id != path_id:
        raise ApiError(422, "LEARNING_JOB_MISMATCH", "路线与请求不一致")
    return queue(db, user.id, body, settings)


@router.get("/jobs")
def jobs(user: CurrentUser, db: Database):
    return [job_view(item) for item in rows(db, LearningJob, user.id, limit=8)]


@router.post("/jobs/{job_id}/retry", status_code=202)
def retry(job_id: int, user: CurrentUser, db: Database):
    lock_user(db, user.id)
    item = own(db, LearningJob, user.id, job_id, lock=True)
    if item.state != "failed" or item.attempt >= 3 or item.error in {"MODEL_CONFIG_CHANGED", "LEARNING_PREVIEW_CHANGED"}:
        raise ApiError(409, "LEARNING_RETRY", "请重新核对发送内容")
    if db.scalar(select(LearningJob.id).where(LearningJob.user_id == user.id, LearningJob.state.in_(ACTIVE)).limit(1)):
        raise ApiError(409, "LEARNING_BUSY", "已有学习任务在处理")
    item.state, item.error, item.attempt = "queued", None, item.attempt + 1
    db.commit()
    return job_view(item)


def assessment_view(item):
    return {**view(item, "topic", "form", "result"),
            "questions": [{key: value for key, value in row.items() if key != "correct"} for row in item.questions],
            "application": {"type": OPEN_FORMATS[item.topic], "question": TOPICS[item.topic]["exercise"],
                            "acceptance": TOPICS[item.topic]["acceptance"]}}


@router.post("/assessments/start", status_code=201)
def start_assessment(body: TopicInput, user: CurrentUser, db: Database):
    topic_for(body.topic)
    lock_user(db, user.id)
    prior = rows(db, LearningAssessment, user.id, LearningAssessment.topic == body.topic, limit=4)
    if prior and prior[0].result is None:
        return assessment_view(prior[0])
    form = (prior[0].form + 1) % 2 if prior else 0
    item = LearningAssessment(user_id=user.id, topic=body.topic, form=form, questions=exam(body.topic, form))
    db.add(item)
    db.commit()
    return assessment_view(item)


@router.get("/assessments")
def assessments(user: CurrentUser, db: Database):
    return [assessment_view(item) for item in rows(db, LearningAssessment, user.id, limit=40)]


@router.post("/assessments/{assessment_id}/submit")
def submit_assessment(assessment_id: int, body: Answers, user: CurrentUser, db: Database):
    lock_user(db, user.id)
    item = own(db, LearningAssessment, user.id, assessment_id, lock=True)
    if item.result is not None:
        if item.result["answers"] != body.answers:
            raise ApiError(409, "LEARNING_ASSESSMENT_SUBMITTED", "该测评已交卷")
        return assessment_view(item)
    questions = {row["id"]: row for row in item.questions}
    if questions.keys() != body.answers.keys() or any(value not in {"0", "1", "2"} for value in body.answers.values()):
        raise ApiError(422, "LEARNING_ASSESSMENT_ANSWERS", "请完成所有题目")
    checked = [{"id": key, "correct": body.answers[key] == row["correct"],
                "answer": row["choices"][int(row["correct"])]} for key, row in questions.items()]
    score = round(100 * sum(row["correct"] for row in checked) / len(checked))
    prior = rows(db, LearningAssessment, user.id, LearningAssessment.topic == item.topic,
                 LearningAssessment.id != item.id, LearningAssessment.result.is_not(None), limit=80)
    seen = {row.form for row in prior}
    mode = "first" if not prior else "reassessment" if item.form not in seen else "practice"
    item.result = {"score": score, "answers": body.answers, "checked": checked, "mode": mode,
                   "version": "learning-bank-1"}
    before = rows(db, LearningMastery, user.id, LearningMastery.topic == item.topic, limit=1)
    old_status = before[0].data["status"] if before else next(
        row["status"] for row in diagnosis(db, user.id)["topics"] if row["topic"] == item.topic)
    if mode != "practice" or (score < 75 and old_status == "verified"):
        status = "verified" if score >= 75 else "unknown"
        event = LearningMastery(user_id=user.id, topic=item.topic, assessment_id=item.id,
                                data={"prior": old_status, "status": status, "score": score,
                                      "reason": "独立知识与应用选择题通过" if status == "verified" else "近期测评需要复练",
                                      "last_verified_at": utc_now().isoformat() + "Z"})
        db.add(event)
        db.flush()
        path = latest(db, LearningPath, user.id)
        if path:
            make_path(db, user.id, path.data["weekly_minutes"], path.data["goal"],
                      "阶段测评后更新先修与复练优先级",
                      interview_report_id=path.data.get("source", {}).get("report_id"))
    db.commit()
    return assessment_view(item)


@router.get("/assessments/{assessment_id}/result")
def assessment_result(assessment_id: int, user: CurrentUser, db: Database):
    return assessment_view(own(db, LearningAssessment, user.id, assessment_id))


@router.get("/progress")
@router.get("/reports")
def progress(user: CurrentUser, db: Database):
    total, completed, minutes = db.execute(select(func.count(LearningTask.id),
        func.sum(LearningTask.status == "completed"), func.sum(LearningTask.actual_minutes))
        .where(LearningTask.user_id == user.id)).one()
    return {"total": total, "completed": int(completed or 0), "minutes": int(minutes or 0),
            "completion_rate": round(100 * int(completed or 0) / total) if total else 0,
            "diagnosis": diagnosis(db, user.id),
            "submissions": db.scalar(select(func.count(LearningSubmission.id)).where(LearningSubmission.user_id == user.id)),
            "evaluations": [view(item, "submission_id", "data") for item in rows(db, LearningEvaluation, user.id, limit=20)],
            "assessments": [assessment_view(item) for item in rows(db, LearningAssessment, user.id, limit=20)],
            "history": [view(item, "topic", "assessment_id", "data") for item in rows(db, LearningMastery, user.id, limit=50)]}

