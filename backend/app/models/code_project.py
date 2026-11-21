from datetime import datetime

from sqlalchemy import ForeignKey, Index, JSON, String, UniqueConstraint, func
from sqlalchemy.dialects.mysql import MEDIUMTEXT
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Record:
    id: Mapped[int] = mapped_column(primary_key=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class CodeProject(Record, Base):
    __tablename__ = "github_repositories"
    __table_args__ = (UniqueConstraint("user_id", "slug", name="uq_code_project_owner_slug"),)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    recommendation_id: Mapped[int | None] = mapped_column(
        ForeignKey("project_recommendations.id", name="fk_workspace_recommendation", ondelete="SET NULL"), index=True)
    slug: Mapped[str] = mapped_column(String(140))
    metadata_json: Mapped[dict] = mapped_column(JSON)
    active_commit: Mapped[str | None] = mapped_column(String(64))


class ProjectSnapshot(Record, Base):
    __tablename__ = "project_snapshots"
    __table_args__ = (UniqueConstraint("project_id", "commit_sha", name="uq_project_commit"),)
    project_id: Mapped[int] = mapped_column(ForeignKey("github_repositories.id", ondelete="CASCADE"), index=True)
    commit_sha: Mapped[str] = mapped_column(String(64))
    data: Mapped[dict] = mapped_column(JSON)


class SnapshotRecord(Record):
    snapshot_id: Mapped[int] = mapped_column(ForeignKey("project_snapshots.id", ondelete="CASCADE"), index=True)


class ProjectFile(SnapshotRecord, Base):
    __tablename__ = "project_files"
    __table_args__ = (UniqueConstraint("snapshot_id", "path", name="uq_project_file_path"),)
    path: Mapped[str] = mapped_column(String(600, collation="utf8mb4_bin"))
    blob_sha: Mapped[str] = mapped_column(String(64))
    size: Mapped[int]
    metadata_json: Mapped[dict] = mapped_column(JSON)
    content: Mapped[str | None] = mapped_column(MEDIUMTEXT)
    index_data: Mapped[dict | None] = mapped_column(JSON(none_as_null=True))


class ProjectLesson(SnapshotRecord, Base):
    __tablename__ = "project_lessons"
    kind: Mapped[str] = mapped_column(String(24))
    data: Mapped[dict] = mapped_column(JSON)


class ProjectQuiz(SnapshotRecord, Base):
    __tablename__ = "code_quizzes"
    data: Mapped[dict] = mapped_column(JSON)


class QuizAttempt(SnapshotRecord, Base):
    __tablename__ = "quiz_attempts"
    quiz_id: Mapped[int] = mapped_column(ForeignKey("code_quizzes.id", ondelete="CASCADE"), index=True)
    data: Mapped[dict] = mapped_column(JSON)


class ProjectTask(Record, Base):
    __tablename__ = "code_project_tasks"
    __table_args__ = (UniqueConstraint("project_id", "request_key", name="uq_code_project_request"),
                      Index("ix_code_project_queue", "state", "id"))
    project_id: Mapped[int] = mapped_column(ForeignKey("github_repositories.id", ondelete="CASCADE"), index=True)
    snapshot_id: Mapped[int | None] = mapped_column(ForeignKey("project_snapshots.id", ondelete="CASCADE"))
    request_key: Mapped[str] = mapped_column(String(64))
    kind: Mapped[str] = mapped_column(String(24))
    payload: Mapped[dict] = mapped_column(JSON)
    state: Mapped[str] = mapped_column(String(16), default="queued")
    attempt: Mapped[int] = mapped_column(default=1)
    started_at: Mapped[datetime | None]
    result_id: Mapped[int | None]
    error_code: Mapped[str | None] = mapped_column(String(64))
