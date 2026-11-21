from hashlib import sha256
from time import time
from urllib.parse import urlsplit

from fastapi import APIRouter, Query, Response
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.api.dependencies import AppSettings, CurrentUser, Database
from app.core.errors import ApiError
from app.models.code_project import CodeProject, ProjectFile, ProjectLesson, ProjectQuiz, ProjectSnapshot, ProjectTask, QuizAttempt
from app.models.discovery import ProjectRecommendation
from app.schemas.code_project import ImportRequest, SelfReport, StudyRequest, StudySubmit
from app.services.code_project_workflow import (architecture_view, create_task, enqueue_study, idle, latest, mastery,
    owned_project, prepare, scoped_record, snapshot_for, task_for)
from app.services.github_service import MAX_READ_BYTES, MAX_READ_FILES, normalize_repo
from app.services.project_knowledge_service import citations, files_for

router = APIRouter(prefix="/code-projects", tags=["project mentor"])

ERROR_TEXT = {
    "GITHUB_RATE_LIMIT": "GitHub 请求受限，请等配额恢复后重试。",
    "GITHUB_PUBLIC_REPO_UNAVAILABLE": "仓库不存在、无法读取或并非公开仓库。",
    "GITHUB_REPO_TOO_LARGE": "仓库超过 20 MiB 上限。",
    "GITHUB_TREE_TOO_LARGE": "目录过大或 GitHub 返回了不完整的文件树。",
    "GITHUB_FILE_UNREADABLE": "文件内容无法解码为 UTF-8 文本。",
    "MODEL_OUTPUT_INVALID": "模型输出未通过结构校验，可以重试。",
    "MODEL_CONFIG_CHANGED": "模型配置已更新，请重新预览。",
}


def project_view(item):
    return {"id": item.id, "slug": item.slug, "url": "https://github.com/" + item.slug,
            "metadata": item.metadata_json, "active_commit": item.active_commit, "created_at": item.created_at,
            "recommendation_id": item.recommendation_id}


def task_view(item):
    return {"id": item.id, "kind": item.kind, "state": item.state, "attempt": item.attempt,
            "result_id": item.result_id, "snapshot_id": item.snapshot_id, "error_code": item.error_code,
            "retry_at": item.payload.get("retry_at") if item.error_code == "GITHUB_RATE_LIMIT" else None,
            "error_message": ERROR_TEXT.get(item.error_code) or ("任务处理失败，可以查看错误代码后重试。" if item.error_code else None)}


def file_view(item, include_content=False):
    data = {"id": item.id, "path": item.path, "size": item.size, "loaded": item.content is not None, **item.metadata_json}
    if include_content:
        data.update(content=item.content, index=item.index_data)
    return data


def lesson_history(db, snapshot, kind):
    rows = db.scalars(select(ProjectLesson).where(ProjectLesson.snapshot_id == snapshot.id,
                     ProjectLesson.kind == kind).order_by(ProjectLesson.id.desc()).limit(50))
    return [{"id": item.id, "created_at": item.created_at, **item.data} for item in rows]


def submit(kind, body, user, db, settings, project_id):
    if body.kind != kind:
        raise ApiError(422, "CODE_TASK_KIND_MISMATCH", "任务与接口不匹配")
    project = owned_project(db, user.id, project_id, lock=True)
    snapshot = snapshot_for(db, project, body.commit)
    task = enqueue_study(db, project, snapshot, body, settings)
    db.commit()
    return task_view(task)


@router.post("/import", status_code=202)
def import_repository(body: ImportRequest, user: CurrentUser, db: Database):
    slug = normalize_repo(body.url)
    if body.recommendation_id is not None:
        require_recommendation(db, user.id, body.recommendation_id)
    query = select(CodeProject).where(CodeProject.user_id == user.id, CodeProject.slug == slug).with_for_update()
    item = db.scalar(query)
    if item is None:
        item = CodeProject(user_id=user.id, slug=slug, metadata_json={})
        db.add(item)
        try:
            db.flush()
        except IntegrityError:
            db.rollback()
            item = db.scalar(query)
            if item is None:
                raise
    if body.recommendation_id is not None:
        item.recommendation_id = body.recommendation_id
    return queue_import(db, item)


def require_recommendation(db, user_id, recommendation_id):
    row = db.scalar(select(ProjectRecommendation).where(ProjectRecommendation.id == recommendation_id,
                    ProjectRecommendation.user_id == user_id, ProjectRecommendation.selected.is_(True)))
    if row is None:
        raise ApiError(404, "CODE_RECOMMENDATION_NOT_FOUND", "未找到本人已选定的项目方案")
    return row


@router.get("/recommendations/{recommendation_id}")
def recommendation_source(recommendation_id: int, user: CurrentUser, db: Database):
    row = require_recommendation(db, user.id, recommendation_id)
    return {"id": row.id, "name": row.data["name"]}


def queue_import(db, item):
    queued = db.scalar(select(ProjectTask).where(ProjectTask.project_id == item.id, ProjectTask.kind == "import",
                       ProjectTask.state.in_(("queued", "running"))).limit(1))
    task = queued or create_task(db, item, "import", {}, sha256(f"import:{int(time()) // 30}".encode()).hexdigest())
    db.commit()
    return {"project": project_view(item), "task": task_view(task)}


@router.get("")
def list_projects(user: CurrentUser, db: Database):
    items = db.scalars(select(CodeProject).where(CodeProject.user_id == user.id).order_by(CodeProject.id.desc()))
    return [project_view(item) for item in items]


@router.post("/{project_id}/refresh", status_code=202)
def refresh(project_id: int, user: CurrentUser, db: Database):
    return queue_import(db, owned_project(db, user.id, project_id, lock=True))


@router.delete("/{project_id}", status_code=204)
def delete_project(project_id: int, user: CurrentUser, db: Database):
    project = owned_project(db, user.id, project_id, lock=True)
    idle(db, project.id)
    db.delete(project)
    db.commit()
    return Response(status_code=204)


@router.get("/{project_id}")
def project_detail(project_id: int, user: CurrentUser, db: Database):
    project = owned_project(db, user.id, project_id)
    snapshots = list(db.scalars(select(ProjectSnapshot).where(ProjectSnapshot.project_id == project.id)
                               .order_by(ProjectSnapshot.id.desc())))
    tasks = db.scalars(select(ProjectTask).where(ProjectTask.project_id == project.id)
                       .order_by(ProjectTask.id.desc()).limit(15))
    return {**project_view(project), "versions": [{"sha": row.commit_sha, "created_at": row.created_at} for row in snapshots],
            "tasks": [task_view(item) for item in tasks]}


@router.get("/{project_id}/files")
def files(project_id: int, user: CurrentUser, db: Database, commit: str | None = None):
    snapshot = snapshot_for(db, owned_project(db, user.id, project_id), commit)
    return [file_view(row) for row in files_for(db, snapshot.id)]


@router.get("/{project_id}/files/{file_id}")
def file_detail(project_id: int, file_id: int, user: CurrentUser, db: Database, commit: str | None = None):
    snapshot = snapshot_for(db, owned_project(db, user.id, project_id), commit)
    return file_view(scoped_record(db, ProjectFile, snapshot.id, file_id), include_content=True)


@router.post("/{project_id}/files/{file_id}/load", status_code=202)
def load_file(project_id: int, file_id: int, user: CurrentUser, db: Database, commit: str | None = None):
    project = owned_project(db, user.id, project_id, lock=True)
    snapshot = snapshot_for(db, project, commit)
    item = scoped_record(db, ProjectFile, snapshot.id, file_id)
    if not item.metadata_json["readable"]:
        raise ApiError(422, "GITHUB_FILE_UNREADABLE", "该文件超限或无法解码")
    if item.content is not None:
        return {"file": file_view(item), "task": None}
    count, size = db.execute(select(func.count(ProjectFile.id), func.coalesce(func.sum(ProjectFile.size), 0))
                             .where(ProjectFile.snapshot_id == snapshot.id, ProjectFile.content.is_not(None))).one()
    if count >= MAX_READ_FILES or size + item.size > MAX_READ_BYTES:
        raise ApiError(422, "CODE_READING_BUDGET", "当前版本已达 40 个文件或 3 MiB 的读取上限")
    task = create_task(db, project, "load", {"file_id": item.id}, sha256(f"load:{item.id}".encode()).hexdigest(), snapshot)
    db.commit()
    return {"file": file_view(item), "task": task_view(task)}


@router.get("/{project_id}/architecture")
def get_architecture(project_id: int, user: CurrentUser, db: Database, commit: str | None = None):
    snapshot = snapshot_for(db, owned_project(db, user.id, project_id), commit)
    return architecture_view(db, snapshot)


@router.get("/{project_id}/knowledge")
def search_knowledge(project_id: int, user: CurrentUser, db: Database, q: str = Query(default="", max_length=350), commit: str | None = None):
    snapshot = snapshot_for(db, owned_project(db, user.id, project_id), commit)
    return {"commit": snapshot.commit_sha, "matches": citations(files_for(db, snapshot.id, loaded=True), q)}


@router.post("/{project_id}/preview")
def preview(project_id: int, body: StudyRequest, user: CurrentUser, db: Database, settings: AppSettings):
    item = owned_project(db, user.id, project_id)
    snapshot = snapshot_for(db, item, body.commit)
    approval, _, view = prepare(db, item, snapshot, body, settings)
    return {"approval": approval, "payload": view, "model_host": urlsplit(settings.llm_base_url or "").hostname}


@router.post("/{project_id}/analyze", status_code=202)
def analyze(project_id: int, body: StudySubmit, user: CurrentUser, db: Database, settings: AppSettings):
    return submit("analyze", body, user, db, settings, project_id)


@router.post("/{project_id}/explain", status_code=202)
def explain(project_id: int, body: StudySubmit, user: CurrentUser, db: Database, settings: AppSettings):
    return submit("explain", body, user, db, settings, project_id)


@router.get("/{project_id}/explanations")
def explanations(project_id: int, user: CurrentUser, db: Database, commit: str | None = None):
    snapshot = snapshot_for(db, owned_project(db, user.id, project_id), commit)
    return lesson_history(db, snapshot, "explain")


@router.post("/{project_id}/chat", status_code=202)
def chat(project_id: int, body: StudySubmit, user: CurrentUser, db: Database, settings: AppSettings):
    return submit("chat", body, user, db, settings, project_id)


@router.get("/{project_id}/chat/history")
def history(project_id: int, user: CurrentUser, db: Database, commit: str | None = None):
    snapshot = snapshot_for(db, owned_project(db, user.id, project_id), commit)
    return lesson_history(db, snapshot, "chat")


@router.post("/{project_id}/quizzes/generate", status_code=202)
def generate_quiz(project_id: int, body: StudySubmit, user: CurrentUser, db: Database, settings: AppSettings):
    return submit("quiz", body, user, db, settings, project_id)


@router.get("/{project_id}/quizzes")
def quizzes(project_id: int, user: CurrentUser, db: Database, commit: str | None = None):
    snapshot = snapshot_for(db, owned_project(db, user.id, project_id), commit)
    return [{"id": item.id, **{key: item.data[key] for key in ("question", "concept", "dimension", "mode", "evidence")}}
            for item in latest(db, ProjectQuiz, snapshot.id)]


@router.post("/{project_id}/quizzes/{quiz_id}/submit", status_code=202)
def submit_answer(project_id: int, quiz_id: int, body: StudySubmit, user: CurrentUser, db: Database, settings: AppSettings):
    if quiz_id != body.quiz_id:
        raise ApiError(422, "CODE_QUIZ_MISMATCH", "请重新选择对应题目")
    return submit("grade", body, user, db, settings, project_id)


@router.get("/{project_id}/mastery-report")
def mastery_report(project_id: int, user: CurrentUser, db: Database, commit: str | None = None):
    snapshot = snapshot_for(db, owned_project(db, user.id, project_id), commit)
    return mastery(db, snapshot)


@router.put("/{project_id}/mastery-report/self-report", status_code=201)
def self_report(project_id: int, body: SelfReport, user: CurrentUser, db: Database, commit: str | None = None):
    snapshot = snapshot_for(db, owned_project(db, user.id, project_id, lock=True), commit)
    item = ProjectLesson(snapshot_id=snapshot.id, kind="self_report", data=body.model_dump())
    db.add(item)
    db.commit()
    return {"id": item.id}


@router.get("/{project_id}/tasks/{task_id}")
def task_status(project_id: int, task_id: int, user: CurrentUser, db: Database):
    owned_project(db, user.id, project_id)
    return task_view(task_for(db, project_id, task_id))


@router.post("/{project_id}/tasks/{task_id}/retry", status_code=202)
def retry(project_id: int, task_id: int, user: CurrentUser, db: Database):
    owned_project(db, user.id, project_id, lock=True)
    task = task_for(db, project_id, task_id)
    idle(db, project_id)
    if task.error_code == "GITHUB_RATE_LIMIT" and (task.payload.get("retry_at") or 0) > time():
        raise ApiError(429, "GITHUB_RATE_LIMIT", "GitHub 配额尚未恢复，请稍后重试")
    if task.state != "failed" or task.attempt >= 3 or task.error_code in {"MODEL_CONFIG_CHANGED", "CODE_PREVIEW_CHANGED"}:
        raise ApiError(409, "CODE_RETRY_UNAVAILABLE", "该任务不可重试，请创建新任务")
    task.state, task.error_code, task.attempt = "queued", None, task.attempt + 1
    db.commit()
    return task_view(task)
