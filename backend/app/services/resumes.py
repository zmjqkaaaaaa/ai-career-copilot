from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.evidence import confirm_facts
from app.core.errors import ApiError
from app.models.resume import Resume, ResumeContent, ResumeJob
from app.schemas.career import StructuredResume
from app.services.resume_storage import storage_path, store_upload

ACTIVE_STATES = ("queued", "running")

def utc_now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)

def owned_resume(db: Session, user_id: int, resume_id: int, *, lock=False, deleting=False) -> Resume:
    statement = select(Resume).where(Resume.id == resume_id, Resume.user_id == user_id)
    if not deleting:
        statement = statement.where(Resume.parse_status != "deleting")
    resume = db.scalar(statement.with_for_update() if lock else statement)
    if resume is None:
        raise ApiError(404, "RESUME_NOT_FOUND", "未找到简历")
    return resume

def latest_content(db: Session, resume_id: int, *, lock=False) -> ResumeContent | None:
    statement = select(ResumeContent).where(ResumeContent.resume_id == resume_id).order_by(ResumeContent.version.desc()).limit(1)
    return db.scalar(statement.with_for_update() if lock else statement)

def require_content(db: Session, resume_id: int, content_id: int | None = None, *, latest=False) -> ResumeContent:
    if content_id is None:
        content = latest_content(db, resume_id)
    else:
        content = db.scalar(select(ResumeContent).where(ResumeContent.id == content_id, ResumeContent.resume_id == resume_id))
    if content is None:
        raise ApiError(404, "RESUME_CONTENT_NOT_FOUND", "简历尚无可查看的解析内容")
    if latest and content.id != latest_content(db, resume_id, lock=True).id:
        raise ApiError(409, "RESUME_VERSION_CHANGED", "内容已有新版本，请刷新后继续")
    return content

def active_job(db: Session, resume_id: int) -> ResumeJob | None:
    return db.scalar(select(ResumeJob).where(ResumeJob.resume_id == resume_id, ResumeJob.state.in_(ACTIVE_STATES))
                     .limit(1).with_for_update())

def create_resume(db: Session, user_id: int, upload) -> Resume:
    key, name, file_type, size = store_upload(upload)
    try:
        resume = Resume(user_id=user_id, storage_key=key, original_filename=name, file_type=file_type, file_size=size)
        db.add(resume)
        db.flush()
        db.refresh(resume)
        db.commit()
    except Exception:
        db.rollback()
        storage_path(key).unlink(missing_ok=True)
        raise
    return resume

def remove_resume(db: Session, user_id: int, resume_id: int) -> None:
    resume = owned_resume(db, user_id, resume_id, lock=True, deleting=True)
    if active_job(db, resume.id):
        raise ApiError(409, "RESUME_BUSY", "简历正在处理，请等任务结束后再删除")
    resume.parse_status = "deleting"
    key = resume.storage_key
    db.commit()
    try:
        storage_path(key).unlink(missing_ok=True)
    except OSError:
        raise ApiError(503, "RESUME_DELETE_FAILED", "暂时无法清理文件，请稍后再删除") from None
    # Resume stays hidden and rejects new jobs if cleanup needs to be retried.
    resume = owned_resume(db, user_id, resume_id, lock=True, deleting=True)
    db.delete(resume)
    db.commit()

def copy_revision(db: Session, source: ResumeContent, **updates: Any) -> ResumeContent:
    fields = {
        "parser_version": source.parser_version, "extracted_text": source.extracted_text,
        "blocks": source.blocks, "model_blocks": source.model_blocks, "structured_data": source.structured_data,
        "metadata_json": source.metadata_json, "confirmed": source.confirmed,
    }
    fields.update(updates)
    revision = ResumeContent(resume_id=source.resume_id, version=source.version + 1, **fields)
    db.add(revision)
    db.flush()
    return revision

def edit_content(db: Session, resume: Resume, content_id: int, facts: StructuredResume) -> ResumeContent:
    if active_job(db, resume.id):
        raise ApiError(409, "RESUME_BUSY", "简历正在处理，请在任务结束后确认")
    source = require_content(db, resume.id, content_id, latest=True)
    if source.model_blocks is None or source.structured_data is None:
        raise ApiError(409, "EXTRACTION_REQUIRED", "请先完成结构化提取")
    confirmed = confirm_facts(facts, source.model_blocks).model_dump(mode="json")
    if source.confirmed and source.structured_data == confirmed:
        return source
    revision = copy_revision(db, source, structured_data=confirmed, confirmed=True)
    db.commit()
    return revision
