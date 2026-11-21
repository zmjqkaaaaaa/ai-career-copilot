from datetime import datetime

from sqlalchemy import JSON, ForeignKey, Index, String, Text, UniqueConstraint, text
from sqlalchemy.dialects.mysql import DATETIME
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

class CareerAnalysis(Base):
    __tablename__ = "career_analyses"
    __table_args__ = (Index("ix_career_analyses_owner_created", "user_id", "created_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    content_id: Mapped[int] = mapped_column(ForeignKey("resume_contents.id", ondelete="CASCADE"))
    target_direction: Mapped[str] = mapped_column(String(150))
    analysis_result: Mapped[dict] = mapped_column(JSON)
    model_name: Mapped[str] = mapped_column(String(150))
    prompt_version: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DATETIME(fsp=6), server_default=text("CURRENT_TIMESTAMP(6)"))

class SkillProfile(Base):
    __tablename__ = "skill_profiles"
    __table_args__ = (UniqueConstraint("analysis_id", "skill_name", name="uq_career_analysis_skill"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    analysis_id: Mapped[int] = mapped_column(ForeignKey("career_analyses.id", ondelete="CASCADE"))
    skill_name: Mapped[str] = mapped_column(String(80))
    skill_category: Mapped[str] = mapped_column(String(24))
    proficiency_level: Mapped[str] = mapped_column(String(24))
    evidence_status: Mapped[str] = mapped_column(String(24))
    analysis_reason: Mapped[str] = mapped_column(Text)

class SkillEvidence(Base):
    __tablename__ = "skill_evidence"

    id: Mapped[int] = mapped_column(primary_key=True)
    skill_profile_id: Mapped[int] = mapped_column(ForeignKey("skill_profiles.id", ondelete="CASCADE"), index=True)
    source_type: Mapped[str] = mapped_column(String(32))
    block_number: Mapped[int]
    source_content: Mapped[str] = mapped_column(Text)

class ResumeOptimization(Base):
    __tablename__ = "resume_optimization_records"

    id: Mapped[int] = mapped_column(primary_key=True)
    content_id: Mapped[int] = mapped_column(ForeignKey("resume_contents.id", ondelete="CASCADE"), index=True)
    original_content: Mapped[str] = mapped_column(Text)
    optimized_content: Mapped[str] = mapped_column(Text)
    optimization_reason: Mapped[str] = mapped_column(Text)
    interview_question: Mapped[str] = mapped_column(Text)
    section: Mapped[str] = mapped_column(String(24))
    needs_evidence: Mapped[bool]
    block_number: Mapped[int]
    confirmed_text: Mapped[str | None] = mapped_column(Text)
    confirmed_at: Mapped[datetime | None] = mapped_column(DATETIME(fsp=6))
    created_at: Mapped[datetime] = mapped_column(DATETIME(fsp=6), server_default=text("CURRENT_TIMESTAMP(6)"))
