from sqlalchemy import func, literal_column, select
from sqlalchemy.dialects.mysql import insert
from sqlalchemy.exc import SQLAlchemyError

from app.models.operations import WorkerHeartbeat

FULL_WORKER = "full"
STRATEGY_WORKER = "strategy"
HEARTBEAT_SECONDS = 10


def heartbeat(factory, role: str):
    with factory.begin() as db:
        statement = insert(WorkerHeartbeat).values(role=role, observed_at=func.utc_timestamp())
        db.execute(statement.on_duplicate_key_update(observed_at=func.utc_timestamp()))


def readiness(db, max_age: int):
    try:
        age = db.scalar(select(func.timestampdiff(
            literal_column("SECOND"), WorkerHeartbeat.observed_at, func.utc_timestamp()
        )).where(WorkerHeartbeat.role == FULL_WORKER))
    except SQLAlchemyError:
        return {"status": "not_ready", "checks": {"database": "unavailable", "worker": "unknown"}}
    alive = age is not None and 0 <= age <= max_age
    return {"status": "ready" if alive else "not_ready",
            "checks": {"database": "ok", "worker": "ok" if alive else "stale"}}
