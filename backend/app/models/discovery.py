from datetime import datetime

from sqlalchemy import ForeignKey, Index, JSON, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base

class Owned:
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

class DiscoverySession(Owned, Base):
    __tablename__ = "discovery_sessions"
    job_match_id: Mapped[int | None] = mapped_column(ForeignKey("job_matches.id", name="fk_discovery_job_match", ondelete="SET NULL"), index=True)
    application_id: Mapped[int | None] = mapped_column(ForeignKey("job_applications.id", name="fk_discovery_application", ondelete="SET NULL"), index=True)
    source_snapshot: Mapped[dict | None] = mapped_column(JSON(none_as_null=True))
    title: Mapped[str] = mapped_column(String(150))
    mode: Mapped[str] = mapped_column(String(16))
    direction: Mapped[str | None] = mapped_column(String(180))
    weekly_hours: Mapped[int | None]
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())

class SessionRecord(Owned):
    session_id: Mapped[int] = mapped_column(ForeignKey("discovery_sessions.id", ondelete="CASCADE"), index=True)

class DiscoveryMessage(SessionRecord, Base):
    __tablename__ = "discovery_messages"
    role: Mapped[str] = mapped_column(String(16))
    content: Mapped[str] = mapped_column(Text)
    details: Mapped[dict | None] = mapped_column(JSON(none_as_null=True))

class InterestRecord(SessionRecord, Base):
    __tablename__ = "interest_records"
    data: Mapped[dict] = mapped_column(JSON)

class PainPoint(SessionRecord, Base):
    __tablename__ = "pain_points"
    data: Mapped[dict] = mapped_column(JSON)
    revision: Mapped[int] = mapped_column(default=1)

class MarketResearchRun(SessionRecord, Base):
    __tablename__ = "market_research_runs"
    pain_point_id: Mapped[int] = mapped_column(ForeignKey("pain_points.id", ondelete="CASCADE"), index=True)
    data: Mapped[dict] = mapped_column(JSON)

class CompetitorRecord(Owned, Base):
    __tablename__ = "competitor_records"
    research_id: Mapped[int] = mapped_column(ForeignKey("market_research_runs.id", ondelete="CASCADE"), index=True)
    data: Mapped[dict] = mapped_column(JSON)

class OpportunityAnalysis(SessionRecord, Base):
    __tablename__ = "opportunity_analyses"
    pain_point_id: Mapped[int] = mapped_column(ForeignKey("pain_points.id", ondelete="CASCADE"), index=True)
    research_id: Mapped[int | None] = mapped_column(ForeignKey("market_research_runs.id", ondelete="SET NULL"))
    data: Mapped[dict] = mapped_column(JSON)

class ProjectRecommendation(SessionRecord, Base):
    __tablename__ = "project_recommendations"
    opportunity_id: Mapped[int] = mapped_column(ForeignKey("opportunity_analyses.id", ondelete="CASCADE"), index=True)
    batch_id: Mapped[int]
    data: Mapped[dict] = mapped_column(JSON)
    favorite: Mapped[bool] = mapped_column(default=False)
    selected: Mapped[bool] = mapped_column(default=False)

class ProductPrd(Owned, Base):
    __tablename__ = "product_prds"
    __table_args__ = (UniqueConstraint("recommendation_id", "version", name="uq_product_prd_version"),)
    recommendation_id: Mapped[int] = mapped_column(ForeignKey("project_recommendations.id", ondelete="CASCADE"))
    version: Mapped[int]
    title: Mapped[str] = mapped_column(String(200))
    content: Mapped[str] = mapped_column(Text)
    origin: Mapped[str] = mapped_column(String(16))
    based_on: Mapped[int | None]

class DiscoveryTask(SessionRecord, Base):
    __tablename__ = "discovery_tasks"
    __table_args__ = (UniqueConstraint("session_id", "request_key", name="uq_discovery_request"),
                      Index("ix_discovery_queue", "state", "id"))
    request_key: Mapped[str] = mapped_column(String(64))
    kind: Mapped[str] = mapped_column(String(24))
    payload: Mapped[dict] = mapped_column(JSON)
    provider: Mapped[str] = mapped_column(String(64))
    state: Mapped[str] = mapped_column(String(16), default="queued")
    attempt: Mapped[int] = mapped_column(default=1)
    started_at: Mapped[datetime | None]
    error_code: Mapped[str | None] = mapped_column(String(64))
    result_id: Mapped[int | None]
