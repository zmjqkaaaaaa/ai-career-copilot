from datetime import UTC, datetime

from sqlalchemy import JSON, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


def utc_now():
    return datetime.now(UTC).replace(tzinfo=None)


class OwnedRecord:
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    created_at: Mapped[datetime] = mapped_column(default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(default=utc_now, onupdate=utc_now)


class ResumeVersion(OwnedRecord, Base):
    __tablename__ = "resume_versions"
    __table_args__ = (UniqueConstraint("user_id", "request_id", name="uq_resume_version_request"),
                      UniqueConstraint("user_id", "series_id", "version_number", name="uq_resume_version_series"))
    request_id: Mapped[str] = mapped_column(String(36))
    fingerprint: Mapped[str] = mapped_column(String(64))
    series_id: Mapped[str] = mapped_column(String(36))
    version_number: Mapped[int]
    previous_id: Mapped[int | None] = mapped_column(ForeignKey("resume_versions.id", ondelete="SET NULL"))
    original_resume_id: Mapped[int | None] = mapped_column(ForeignKey("resumes.id", ondelete="SET NULL"))
    content_id: Mapped[int | None] = mapped_column(ForeignKey("resume_contents.id", ondelete="SET NULL"))
    target_job_id: Mapped[int | None] = mapped_column(ForeignKey("job_positions.id", ondelete="SET NULL"))
    job_revision: Mapped[int | None]
    version_name: Mapped[str] = mapped_column(String(150))
    target_position: Mapped[str | None] = mapped_column(String(150))
    content: Mapped[list] = mapped_column(JSON)
    change_summary: Mapped[str] = mapped_column(String(1000))


class JobApplication(OwnedRecord, Base):
    __tablename__ = "job_applications"
    __table_args__ = (UniqueConstraint("user_id", "request_id", name="uq_application_request"),
                      UniqueConstraint("user_id", "job_id", name="uq_application_job"),
                      Index("ix_application_owner_date", "user_id", "applied_at"),
                      Index("ix_application_board", "user_id", "current_status", "updated_at", "id"))
    request_id: Mapped[str] = mapped_column(String(36))
    fingerprint: Mapped[str] = mapped_column(String(64))
    job_id: Mapped[int] = mapped_column(ForeignKey("job_positions.id", ondelete="RESTRICT"))
    resume_version_id: Mapped[int | None] = mapped_column(ForeignKey("resume_versions.id", ondelete="RESTRICT"))
    snapshot: Mapped[dict] = mapped_column(JSON)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)
    channel: Mapped[str | None] = mapped_column(String(150))
    applied_at: Mapped[datetime | None]
    current_status: Mapped[str] = mapped_column(String(24))
    revision: Mapped[int] = mapped_column(default=1)
    valid_submission: Mapped[bool] = mapped_column(default=True)


class ApplicationStatusHistory(Base):
    __tablename__ = "application_status_history"
    __table_args__ = (UniqueConstraint("application_id", "request_id", name="uq_application_history_request"),
                      Index("ix_application_history_status", "application_id", "new_status"))
    id: Mapped[int] = mapped_column(primary_key=True)
    application_id: Mapped[int] = mapped_column(ForeignKey("job_applications.id", ondelete="CASCADE"))
    request_id: Mapped[str] = mapped_column(String(36))
    previous_status: Mapped[str | None] = mapped_column(String(24))
    new_status: Mapped[str] = mapped_column(String(24))
    changed_at: Mapped[datetime] = mapped_column(default=utc_now)
    notes: Mapped[str | None] = mapped_column(String(1000))


class InterviewSchedule(OwnedRecord, Base):
    __tablename__ = "interview_schedules"
    __table_args__ = (UniqueConstraint("user_id", "request_id", name="uq_interview_schedule_request"),
                      Index("ix_interview_schedule_owner_time", "user_id", "scheduled_at"))
    request_id: Mapped[str] = mapped_column(String(36))
    fingerprint: Mapped[str] = mapped_column(String(64))
    application_id: Mapped[int] = mapped_column(ForeignKey("job_applications.id", ondelete="CASCADE"), index=True)
    scheduled_at: Mapped[datetime]
    ends_at: Mapped[datetime]
    timezone: Mapped[str] = mapped_column(String(80))
    revision: Mapped[int] = mapped_column(default=1)
    details: Mapped[dict] = mapped_column(JSON)


class JobStrategyReport(OwnedRecord, Base):
    __tablename__ = "job_strategy_reports"
    __table_args__ = (UniqueConstraint("user_id", "fingerprint", name="uq_job_strategy_snapshot"),)
    fingerprint: Mapped[str] = mapped_column(String(64))
    statistics: Mapped[dict] = mapped_column(JSON)
    analysis: Mapped[dict | None] = mapped_column(JSON(none_as_null=True))
    state: Mapped[str] = mapped_column(String(16), default="queued", index=True)
    attempt: Mapped[int] = mapped_column(default=1, server_default="1")
    started_at: Mapped[datetime | None]
    error_code: Mapped[str | None] = mapped_column(String(64))
    provider_key: Mapped[str] = mapped_column(String(64))
    model_name: Mapped[str] = mapped_column(String(150))
    prompt_version: Mapped[str] = mapped_column(String(32))
