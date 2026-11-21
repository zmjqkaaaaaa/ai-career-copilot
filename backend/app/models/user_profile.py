from datetime import datetime
from typing import Any

from sqlalchemy import JSON, ForeignKey, String, UniqueConstraint, text
from sqlalchemy.dialects.mysql import DATETIME
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

class UserProfile(Base):
    __tablename__ = "user_profiles"
    __table_args__ = (UniqueConstraint("user_id", name="uq_user_profiles_user_id"),
                      {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4"})

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", name="fk_user_profiles_user_id_users", ondelete="CASCADE"))
    real_name: Mapped[str | None] = mapped_column(String(100))
    undergraduate_school: Mapped[str | None] = mapped_column(String(150))
    undergraduate_major: Mapped[str | None] = mapped_column(String(150))
    undergraduate_degree: Mapped[str | None] = mapped_column(String(80))
    graduate_school: Mapped[str | None] = mapped_column(String(150))
    graduate_major: Mapped[str | None] = mapped_column(String(150))
    graduation_year: Mapped[int | None]
    target_position: Mapped[str | None] = mapped_column(String(150))
    interested_industries: Mapped[list[str]] = mapped_column(JSON)
    skills: Mapped[list[str]] = mapped_column(JSON)
    internship_experience: Mapped[list[dict[str, Any]]] = mapped_column(JSON)
    project_experience: Mapped[list[dict[str, Any]]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DATETIME(fsp=6), server_default=text("CURRENT_TIMESTAMP(6)"))
    updated_at: Mapped[datetime] = mapped_column(DATETIME(fsp=6), server_default=text("CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6)"))
