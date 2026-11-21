from datetime import datetime
from sqlalchemy import ForeignKey, Index, JSON, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base


class Owned:
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class LearningDiagnosis(Owned, Base):
    __tablename__ = "learning_diagnoses"
    data: Mapped[dict] = mapped_column(JSON)


class LearningPath(Owned, Base):
    __tablename__ = "learning_paths"
    __table_args__ = (UniqueConstraint("user_id", "version", name="uq_learning_path_version"),)
    version: Mapped[int]
    fingerprint: Mapped[str] = mapped_column(String(64))
    data: Mapped[dict] = mapped_column(JSON)


class LearningTask(Owned, Base):
    __tablename__ = "learning_tasks"
    __table_args__ = (UniqueConstraint("user_id", "task_key", name="uq_learning_daily_key"),)
    task_key: Mapped[str] = mapped_column(String(120))
    topic: Mapped[str] = mapped_column(String(40))
    due: Mapped[str] = mapped_column(String(10))
    status: Mapped[str] = mapped_column(String(20), default="pending")
    actual_minutes: Mapped[int] = mapped_column(default=0)
    data: Mapped[dict] = mapped_column(JSON)


class LearningSession(Owned, Base):
    __tablename__ = "learning_sessions"
    topic: Mapped[str] = mapped_column(String(40))
    mode: Mapped[str] = mapped_column(String(24))
    summary: Mapped[dict] = mapped_column(JSON)


class LearningMessage(Owned, Base):
    __tablename__ = "learning_messages"
    session_id: Mapped[int] = mapped_column(ForeignKey("learning_sessions.id", ondelete="CASCADE"), index=True)
    role: Mapped[str] = mapped_column(String(12))
    data: Mapped[dict] = mapped_column(JSON)


class LearningResource(Owned, Base):
    __tablename__ = "learning_resources"
    topic: Mapped[str] = mapped_column(String(40))
    data: Mapped[dict] = mapped_column(JSON)


class LearningSubmission(Owned, Base):
    __tablename__ = "learning_submissions"
    __table_args__ = (UniqueConstraint("user_id", "topic", "version", name="uq_learning_submission_version"),)
    topic: Mapped[str] = mapped_column(String(40))
    version: Mapped[int]
    request_id: Mapped[str] = mapped_column(String(36))
    data: Mapped[dict] = mapped_column(JSON)


class LearningEvaluation(Owned, Base):
    __tablename__ = "learning_evaluations"
    submission_id: Mapped[int] = mapped_column(ForeignKey("learning_submissions.id", ondelete="CASCADE"), unique=True)
    data: Mapped[dict] = mapped_column(JSON)


class LearningAssessment(Owned, Base):
    __tablename__ = "learning_assessments"
    topic: Mapped[str] = mapped_column(String(40))
    form: Mapped[int]
    questions: Mapped[list] = mapped_column(JSON)
    result: Mapped[dict | None] = mapped_column(JSON(none_as_null=True))


class LearningMastery(Owned, Base):
    __tablename__ = "learning_mastery_history"
    assessment_id: Mapped[int] = mapped_column(ForeignKey("learning_assessments.id", ondelete="CASCADE"), unique=True)
    topic: Mapped[str] = mapped_column(String(40))
    data: Mapped[dict] = mapped_column(JSON)


class LearningJob(Owned, Base):
    __tablename__ = "learning_jobs"
    __table_args__ = (UniqueConstraint("user_id", "request_key", name="uq_learning_job_key"),
                      Index("ix_learning_jobs_queue", "state", "id"))
    request_key: Mapped[str] = mapped_column(String(64))
    kind: Mapped[str] = mapped_column(String(16))
    state: Mapped[str] = mapped_column(String(16), default="queued")
    attempt: Mapped[int] = mapped_column(default=1)
    started_at: Mapped[datetime | None]
    error: Mapped[str | None] = mapped_column(String(64))
    payload: Mapped[dict] = mapped_column(JSON)

