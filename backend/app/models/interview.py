from datetime import datetime

from sqlalchemy import ForeignKey, Index, JSON, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Record:
    id: Mapped[int] = mapped_column(primary_key=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class InterviewSession(Record, Base):
    __tablename__ = "interview_sessions"
    __table_args__ = (UniqueConstraint("user_id", "request_id", name="uq_interview_request"),
                      Index("ix_interview_owner", "user_id", "id"),
                      Index("ix_interview_deadline", "state", "deadline_at"))
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    request_id: Mapped[str] = mapped_column(String(36))
    target: Mapped[str] = mapped_column(String(150))
    settings: Mapped[dict] = mapped_column(JSON)
    context: Mapped[dict] = mapped_column(JSON)
    state: Mapped[str] = mapped_column(String(16), default="ready")
    revision: Mapped[int] = mapped_column(default=0)
    started_at: Mapped[datetime | None]
    deadline_at: Mapped[datetime | None]
    finished_at: Mapped[datetime | None]
    finish_reason: Mapped[str | None] = mapped_column(String(24))


class SessionRecord(Record):
    session_id: Mapped[int] = mapped_column(ForeignKey("interview_sessions.id", ondelete="CASCADE"), index=True)


class InterviewQuestion(SessionRecord, Base):
    __tablename__ = "interview_questions"
    __table_args__ = (UniqueConstraint("session_id", "ordinal", name="uq_interview_ordinal"),)
    ordinal: Mapped[int]
    stage: Mapped[str] = mapped_column(String(20))
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("interview_questions.id", ondelete="CASCADE"))
    data: Mapped[dict] = mapped_column(JSON)


class InterviewAnswer(SessionRecord, Base):
    __tablename__ = "interview_answers"
    question_id: Mapped[int] = mapped_column(ForeignKey("interview_questions.id", ondelete="CASCADE"), unique=True)
    text: Mapped[str] = mapped_column(Text)
    data: Mapped[dict] = mapped_column(JSON)


class InterviewReport(Record, Base):
    __tablename__ = "interview_reports"
    session_id: Mapped[int] = mapped_column(ForeignKey("interview_sessions.id", ondelete="CASCADE"), unique=True)
    data: Mapped[dict] = mapped_column(JSON)


class InterviewTrainingTask(Record, Base):
    __tablename__ = "interview_training_tasks"
    report_id: Mapped[int] = mapped_column(ForeignKey("interview_reports.id", ondelete="CASCADE"), index=True)
    state: Mapped[str] = mapped_column(String(16), default="todo")
    due_at: Mapped[datetime]
    completed_at: Mapped[datetime | None]
    data: Mapped[dict] = mapped_column(JSON)


class InterviewTask(SessionRecord, Base):
    __tablename__ = "interview_tasks"
    __table_args__ = (UniqueConstraint("session_id", "request_key", name="uq_interview_task"),
                      Index("ix_interview_queue", "state", "id"))
    request_key: Mapped[str] = mapped_column(String(64))
    kind: Mapped[str] = mapped_column(String(12))
    state: Mapped[str] = mapped_column(String(16), default="queued")
    attempt: Mapped[int] = mapped_column(default=1)
    revision: Mapped[int]
    payload: Mapped[dict] = mapped_column(JSON)
    started_at: Mapped[datetime | None]
    error_code: Mapped[str | None] = mapped_column(String(64))
