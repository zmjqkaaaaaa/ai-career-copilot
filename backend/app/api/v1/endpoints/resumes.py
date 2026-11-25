from typing import Annotated

from fastapi import APIRouter, File, Query, UploadFile
from sqlalchemy import select

from app.ai.evidence import redact_blocks
from app.api.dependencies import AppSettings, CurrentUser, Database
from app.core.errors import ApiError
from app.models.resume import Resume, ResumeJob
from app.schemas.career import (
    Block, ConfirmOptimization, ContentEdit, ContentRead, ExtractTrigger, JobRead, LocalDraftRequest, OptimizationRead,
    OptimizeRequest, ParseTrigger, ResumeRead,
)
from app.services.career import confirm_optimization, optimization_query
from app.services.resume_jobs import job_history, start_job
from app.services.resumes import create_local_draft, create_resume, edit_content, owned_resume, remove_resume, require_content
from app.services.worker_health import FULL_WORKER, HEARTBEAT_SECONDS, RESUME_WORKER, has_recent_heartbeat

router = APIRouter(prefix="/resumes", tags=["resumes"])
jobs_router = APIRouter(prefix="/resume-jobs", tags=["resume-jobs"])

@router.post("/upload", status_code=201, response_model=ResumeRead)
def upload_resume(file: Annotated[UploadFile, File()], user: CurrentUser, db: Database):
    return create_resume(db, user.id, file)

@router.get("", response_model=list[ResumeRead])
def list_resumes(user: CurrentUser, db: Database, offset: Annotated[int, Query(ge=0)] = 0):
    return db.scalars(select(Resume).where(Resume.user_id == user.id)
                      .order_by(Resume.id.desc()).offset(offset).limit(50)).all()

@router.get("/{resume_id}", response_model=ResumeRead)
def read_resume(resume_id: int, user: CurrentUser, db: Database):
    return owned_resume(db, user.id, resume_id, deleting=True)

@router.delete("/{resume_id}", status_code=204)
def delete_resume(resume_id: int, user: CurrentUser, db: Database):
    remove_resume(db, user.id, resume_id)

@router.post("/{resume_id}/parse", status_code=202, response_model=JobRead)
def parse(resume_id: int, user: CurrentUser, db: Database, settings: AppSettings, body: ParseTrigger = ParseTrigger()):
    return start_job(db, user.id, resume_id, "parse", body, settings)

@router.post("/{resume_id}/extract", status_code=202, response_model=JobRead)
def extract(resume_id: int, body: ExtractTrigger, user: CurrentUser, db: Database, settings: AppSettings):
    return start_job(db, user.id, resume_id, "extract", body, settings)

@router.post("/{resume_id}/local-draft", status_code=201, response_model=ContentRead)
def local_draft(resume_id: int, body: LocalDraftRequest, user: CurrentUser, db: Database):
    resume = owned_resume(db, user.id, resume_id, lock=True)
    return create_local_draft(db, resume, body.content_id, body.hidden_blocks)

@router.get("/{resume_id}/content", response_model=ContentRead)
def read_content(resume_id: int, user: CurrentUser, db: Database, content_id: Annotated[int | None, Query(gt=0)] = None):
    owned_resume(db, user.id, resume_id)
    return require_content(db, resume_id, content_id)

@router.get("/{resume_id}/preview", response_model=list[Block])
def read_preview(resume_id: int, user: CurrentUser, db: Database, content_id: Annotated[int, Query(gt=0)]):
    owned_resume(db, user.id, resume_id)
    return redact_blocks(require_content(db, resume_id, content_id).blocks)

@router.put("/{resume_id}/content", response_model=ContentRead)
def update_content(resume_id: int, body: ContentEdit, user: CurrentUser, db: Database):
    resume = owned_resume(db, user.id, resume_id, lock=True)
    return edit_content(db, resume, body.content_id, body.structured_data)

@router.post("/{resume_id}/optimize", status_code=202, response_model=JobRead)
def optimize(resume_id: int, body: OptimizeRequest, user: CurrentUser, db: Database, settings: AppSettings):
    return start_job(db, user.id, resume_id, "optimize", body, settings)

@router.get("/{resume_id}/optimizations", response_model=list[OptimizationRead])
def optimizations(resume_id: int, user: CurrentUser, db: Database, content_id: Annotated[int | None, Query(gt=0)] = None):
    owned_resume(db, user.id, resume_id)
    statement = optimization_query(resume_id)
    if content_id:
        statement = statement.where(statement.selected_columns.content_id == content_id)
    return db.scalars(statement.order_by(statement.selected_columns.id.desc()).limit(50)).all()

@router.post("/{resume_id}/optimizations/{record_id}/confirm", response_model=OptimizationRead)
def confirm(resume_id: int, record_id: int, body: ConfirmOptimization, user: CurrentUser, db: Database):
    owned_resume(db, user.id, resume_id, lock=True)
    return confirm_optimization(db, resume_id, record_id, body.text)

@router.get("/{resume_id}/jobs", response_model=list[JobRead])
def jobs(resume_id: int, user: CurrentUser, db: Database):
    owned_resume(db, user.id, resume_id)
    return job_history(db, resume_id)

@jobs_router.get("/{job_id}", response_model=JobRead)
def job_progress(job_id: int, user: CurrentUser, db: Database):
    job = db.scalar(select(ResumeJob).join(Resume).where(
        ResumeJob.id == job_id, Resume.user_id == user.id, Resume.parse_status != "deleting",
    ))
    if job is None:
        raise ApiError(404, "RESUME_JOB_NOT_FOUND", "未找到简历任务")
    available = has_recent_heartbeat(db, (FULL_WORKER, RESUME_WORKER), 3 * HEARTBEAT_SECONDS) if job.state in {"queued", "running"} else None
    return JobRead.model_validate(job).model_copy(update={"worker_available": available})
