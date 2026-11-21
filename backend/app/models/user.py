from datetime import datetime

from sqlalchemy import Boolean, String, UniqueConstraint, text
from sqlalchemy.dialects.mysql import DATETIME
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

class User(Base):
    __tablename__ = "users"
    __table_args__ = (UniqueConstraint("email", name="uq_users_email"),
                      {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4"})

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(254, collation="utf8mb4_bin"))
    username: Mapped[str] = mapped_column(String(64))
    password_hash: Mapped[str] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, server_default=text("1"))
    created_at: Mapped[datetime] = mapped_column(DATETIME(fsp=6), server_default=text("CURRENT_TIMESTAMP(6)"))
    updated_at: Mapped[datetime] = mapped_column(DATETIME(fsp=6), server_default=text("CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6)"))
