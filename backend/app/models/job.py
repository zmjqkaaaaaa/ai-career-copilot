from datetime import datetime
from sqlalchemy import Boolean, ForeignKey, Index, JSON, String, Text, UniqueConstraint, false, func
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base

class JobPosition(Base):
    __tablename__ = "job_positions"
    __table_args__ = (Index("ix_job_owner_id", "user_id", "id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    position_name: Mapped[str] = mapped_column(String(150))
    company_name: Mapped[str | None] = mapped_column(String(150))
    location: Mapped[str | None] = mapped_column(String(150))
    job_type: Mapped[str | None] = mapped_column(String(32))
    salary_range: Mapped[str | None] = mapped_column(String(100))
    source_url: Mapped[str | None] = mapped_column(String(1000))
    job_description: Mapped[str] = mapped_column(Text)
    parsed: Mapped[dict | None] = mapped_column(JSON(none_as_null=True))
    revision: Mapped[int] = mapped_column(default=0)
    confirmed: Mapped[bool] = mapped_column(default=False)
    favorite: Mapped[bool] = mapped_column(Boolean, server_default=false())
    archived: Mapped[bool] = mapped_column(Boolean, server_default=false())
    discovery_metadata: Mapped[dict | None] = mapped_column(JSON(none_as_null=True))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())

class JobRequirement(Base):
    __tablename__ = "job_requirements"
    __table_args__ = (UniqueConstraint("job_id", "revision", "ordinal", name="uq_job_requirement_revision"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("job_positions.id", ondelete="CASCADE"))
    revision: Mapped[int]
    ordinal: Mapped[int]
    requirement: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

class JobMatch(Base):
    __tablename__ = "job_matches"
    __table_args__ = (Index("ix_job_match_owner", "user_id", "id"), UniqueConstraint("job_id", "fingerprint", name="uq_job_match_input"))
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    job_id: Mapped[int] = mapped_column(ForeignKey("job_positions.id", ondelete="CASCADE"))
    content_id: Mapped[int] = mapped_column(ForeignKey("resume_contents.id", ondelete="CASCADE"), index=True)
    analysis_id: Mapped[int | None] = mapped_column(ForeignKey("career_analyses.id", ondelete="SET NULL"))
    revision: Mapped[int]
    scoring_version: Mapped[str] = mapped_column(String(40))
    fingerprint: Mapped[str] = mapped_column(String(64))
    overall_score: Mapped[float | None]
    evidence_coverage: Mapped[float | None]
    score_details: Mapped[dict] = mapped_column(JSON)
    recommendations: Mapped[dict | None] = mapped_column(JSON(none_as_null=True))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

class JobSkillGap(Base):
    __tablename__ = "job_skill_gaps"
    id: Mapped[int] = mapped_column(primary_key=True)
    match_id: Mapped[int] = mapped_column(ForeignKey("job_matches.id", ondelete="CASCADE"), index=True)
    result: Mapped[dict] = mapped_column(JSON)

class JobAnalysisTask(Base):
    __tablename__ = "job_analysis_tasks"
    __table_args__ = (UniqueConstraint("job_id", "kind", "fingerprint", name="uq_job_analysis_task_input"),
                      Index("ix_job_analysis_queue", "state", "id"))
    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("job_positions.id", ondelete="CASCADE"))
    match_id: Mapped[int | None] = mapped_column(ForeignKey("job_matches.id", ondelete="CASCADE"))
    kind: Mapped[str] = mapped_column(String(24))
    fingerprint: Mapped[str] = mapped_column(String(64))
    payload: Mapped[dict] = mapped_column(JSON)
    state: Mapped[str] = mapped_column(String(16), default="queued")
    attempt: Mapped[int] = mapped_column(default=1)
    started_at: Mapped[datetime | None]
    error_code: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
