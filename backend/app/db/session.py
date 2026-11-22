from functools import lru_cache

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings

@lru_cache
def session_factory() -> sessionmaker[Session]:
    settings = get_settings()
    engine = create_engine(
        settings.database_url, pool_pre_ping=True, pool_recycle=settings.db_pool_recycle_seconds,
        pool_size=settings.db_pool_size, max_overflow=settings.db_max_overflow,
        pool_timeout=5, hide_parameters=True,
        connect_args={"init_command": "SET time_zone = '+00:00'", "connect_timeout": 5},
    )
    return sessionmaker(engine, expire_on_commit=False)

def get_db():
    with session_factory()() as session:
        yield session
