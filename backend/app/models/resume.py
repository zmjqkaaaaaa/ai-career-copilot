from datetime import datetime

from sqlalchemy import JSON, ForeignKey, Index, String, UniqueConstraint, text
from sqlalchemy.dialects.mysql import DATETIME, MEDIUMTEXT
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

class Resume(Base):
    __tablename__ = "resumes"
    __table_args__ = (Index("ix_resumes_user_created", "user_id", "created_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    original_filename: Mapped[str] = mapped_column(String(255))
    storage_key: Mapped[str] = mapped_column(String(64), unique=True)
    file_type: Mapped[str] = mapped_column(String(4))
    file_size: Mapped[int]
    parse_status: Mapped[str] = mapped_column(String(24), default="uploaded")
    parse_error: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DATETIME(fsp=6), server_default=text("CURRENT_TIMESTAMP(6)"))
    updated_at: Mapped[datetime] = mapped_column(DATETIME(fsp=6), server_default=text("CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6)"))

class ResumeContent(Base):
    __tablename__ = "resume_contents"
    __table_args__ = (UniqueConstraint("resume_id", "version", name="uq_resume_content_version"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    resume_id: Mapped[int] = mapped_column(ForeignKey("resumes.id", ondelete="CASCADE"))
    version: Mapped[int]
    parser_version: Mapped[str] = mapped_column(String(32))
    extracted_text: Mapped[str] = mapped_column(MEDIUMTEXT)
    blocks: Mapped[list] = mapped_column(JSON)
    model_blocks: Mapped[list | None] = mapped_column(JSON(none_as_null=True))
    structured_data: Mapped[dict | None] = mapped_column(JSON(none_as_null=True))
    metadata_json: Mapped[dict | None] = mapped_column(JSON(none_as_null=True))
    confirmed: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(DATETIME(fsp=6), server_default=text("CURRENT_TIMESTAMP(6)"))

class ResumeJob(Base):
    __tablename__ = "resume_jobs"
    __table_args__ = (
        UniqueConstraint("resume_id", "kind", "dedupe_key", name="uq_resume_job_request"),
        Index("ix_resume_jobs_queue", "state", "id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    resume_id: Mapped[int] = mapped_column(ForeignKey("resumes.id", ondelete="CASCADE"))
    kind: Mapped[str] = mapped_column(String(16))
    dedupe_key: Mapped[str] = mapped_column(String(64))
    state: Mapped[str] = mapped_column(String(16), default="queued")
    attempt: Mapped[int] = mapped_column(default=1)
    payload: Mapped[dict] = mapped_column(JSON)
    result_id: Mapped[int | None]
    error_code: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DATETIME(fsp=6), server_default=text("CURRENT_TIMESTAMP(6)"))
    started_at: Mapped[datetime | None] = mapped_column(DATETIME(fsp=6))
    scheduled_at: Mapped[datetime] = mapped_column(DATETIME(fsp=6), server_default=text("CURRENT_TIMESTAMP(6)"))
    finished_at: Mapped[datetime | None] = mapped_column(DATETIME(fsp=6))
