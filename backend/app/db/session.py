from functools import lru_cache

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings

@lru_cache
def session_factory() -> sessionmaker[Session]:
    engine = create_engine(
        get_settings().database_url, pool_pre_ping=True, pool_recycle=1800,
        connect_args={"init_command": "SET time_zone = '+00:00'"},
    )
    return sessionmaker(engine, expire_on_commit=False)

def get_db():
    with session_factory()() as session:
        yield session
