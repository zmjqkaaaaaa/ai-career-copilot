from datetime import datetime
from decimal import Decimal

from sqlalchemy import BigInteger, ForeignKey, Index, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class WorkerHeartbeat(Base):
    __tablename__ = "worker_heartbeats"

    role: Mapped[str] = mapped_column(String(16), primary_key=True)
    observed_at: Mapped[datetime] = mapped_column(server_default=func.now())


class PendingFileDeletion(Base):
    __tablename__ = "pending_file_deletions"

    storage_key: Mapped[str] = mapped_column(String(32), primary_key=True)
    requested_at: Mapped[datetime] = mapped_column(server_default=func.now())
    next_attempt_at: Mapped[datetime] = mapped_column(server_default=func.now(), index=True)
    attempts: Mapped[int] = mapped_column(default=0)


class AuthRateWindow(Base):
    __tablename__ = "auth_rate_windows"
    fingerprint: Mapped[str] = mapped_column(String(64), primary_key=True)
    window_start: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    expires_at: Mapped[int] = mapped_column(BigInteger, index=True)
    hits: Mapped[int]


class LlmCallMetric(Base):
    __tablename__ = "llm_call_metrics"
    __table_args__ = (
        Index("ix_llm_metric_owner_time", "user_id", "created_at"),
        Index("ix_llm_metric_task", "module", "task_id", "attempt"),
        Index("ix_llm_metric_time", "created_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    module: Mapped[str] = mapped_column(String(32))
    task_id: Mapped[int]
    attempt: Mapped[int]
    model: Mapped[str] = mapped_column(String(150))
    operation: Mapped[str] = mapped_column(String(64))
    prompt_version: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(64))
    duration_ms: Mapped[int]
    queue_wait_ms: Mapped[int | None]
    input_tokens: Mapped[int | None]
    output_tokens: Mapped[int | None]
    estimated_cost: Mapped[Decimal | None] = mapped_column(Numeric(16, 8))
    currency: Mapped[str | None] = mapped_column(String(3))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
