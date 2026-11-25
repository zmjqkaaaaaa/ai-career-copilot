from sqlalchemy import func, literal_column, select
from sqlalchemy.dialects.mysql import insert
from sqlalchemy.exc import SQLAlchemyError

from app.models.operations import WorkerHeartbeat

FULL_WORKER = "full"
RESUME_WORKER = "resume"
JOB_WORKER = "job_matching"
STRATEGY_WORKER = "strategy"
HEARTBEAT_SECONDS = 10


def heartbeat(factory, role: str):
    with factory.begin() as db:
        statement = insert(WorkerHeartbeat).values(role=role, observed_at=func.utc_timestamp())
        db.execute(statement.on_duplicate_key_update(observed_at=func.utc_timestamp()))


def has_recent_heartbeat(db, roles, max_age: int):
    age = db.scalar(select(func.min(func.timestampdiff(
        literal_column("SECOND"), WorkerHeartbeat.observed_at, func.utc_timestamp()
    ))).where(WorkerHeartbeat.role.in_(roles), WorkerHeartbeat.observed_at <= func.utc_timestamp()))
    return age is not None and age <= max_age


def readiness(db, max_age: int):
    try:
        alive = has_recent_heartbeat(db, (FULL_WORKER,), max_age)
    except SQLAlchemyError:
        return {"status": "not_ready", "checks": {"database": "unavailable", "worker": "unknown"}}
    return {"status": "ready" if alive else "not_ready",
            "checks": {"database": "ok", "worker": "ok" if alive else "stale"}}
