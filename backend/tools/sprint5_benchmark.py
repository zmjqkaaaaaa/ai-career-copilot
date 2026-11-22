"""Compare API timings and response sizes using only generated data in the test database."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
import json
from math import ceil
from pathlib import Path
from statistics import median
from time import perf_counter, sleep
from threading import Event
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import delete, insert

from app.core.config import get_settings
from app.db.session import session_factory
from app.main import create_app
from app.models.application import ApplicationStatusHistory, InterviewSchedule, JobApplication
from app.models.job import JobPosition
from app.models.user import User
from app.services.resumes import utc_now
from app.services.worker_scheduler import run_queues


def seed(user_id, size):
    with session_factory().begin() as db:
        jobs = [JobPosition(user_id=user_id, position_name=f"合成岗位 {i % 12}", company_name="测试公司",
                            location="测试城市", job_description="合成岗位职责和要求。" * 150)
                for i in range(size)]
        db.add_all(jobs)
        db.flush()
        now = utc_now().replace(microsecond=0)
        records = [
            JobApplication(user_id=user_id, job_id=job.id, request_id=str(uuid4()), fingerprint="0" * 64,
                           snapshot={"company": "测试公司", "position": job.position_name, "jd": job.job_description,
                                     "requirements": [], "job_revision": 0},
                           metadata_json={"next_action": "核对测试样例" if i % 7 == 0 else None},
                           applied_at=now - timedelta(days=i % 30, minutes=i % 15),
                           current_status=("offer", "interview_1", "written_test", "applied")[i % 4],
                           valid_submission=i % 11 != 0)
            for i, job in enumerate(jobs)
        ]
        db.add_all(records)
        db.flush()
        if records:
            db.execute(insert(ApplicationStatusHistory), [
                {"application_id": row.id, "request_id": str(uuid4()), "previous_status": "wishlist", "new_status": status}
                for row in records for status in ("applied", "written_test", row.current_status)
            ])
            db.execute(insert(InterviewSchedule), [
                {"user_id": user_id, "application_id": row.id, "request_id": str(uuid4()), "fingerprint": "0" * 64,
                 "scheduled_at": now + timedelta(days=1, hours=i + 1),
                 "ends_at": now + timedelta(days=1, hours=i + 2), "timezone": "UTC",
                 "details": {"result": "passed" if i % 3 else "cancelled", "preparation_notes": "合成说明" * 40}}
                for i, row in enumerate(records) if i % 4 == 0
            ])


def measure(client, headers, path, repetitions, concurrency):
    response = client.get(path, headers=headers)
    response.raise_for_status()

    def get(_):
        at = perf_counter()
        reply = client.get(path, headers=headers)
        elapsed = (perf_counter() - at) * 1000
        reply.raise_for_status()
        return elapsed, len(reply.content)

    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        results = list(pool.map(get, range(repetitions)))
    values = sorted(item[0] for item in results)
    return {"p50_ms": round(median(values), 2), "p95_ms": round(values[ceil(0.95 * len(values)) - 1], 2),
            "response_bytes": int(median(item[1] for item in results))}


def dataset(size, repetitions, concurrency, board):
    account = None
    try:
        with TestClient(create_app()) as client:
            email, password = f"benchmark-{uuid4().hex}@example.com", "SyntheticBenchmark-55"
            response = client.post("/api/v1/auth/register", json={"email": email, "password": password, "username": "Benchmark"})
            response.raise_for_status()
            account = response.json()["id"]
            seed(account, size)
            reply = client.post("/api/v1/auth/login", data={"username": email, "password": password})
            reply.raise_for_status()
            headers = {"Authorization": "Bearer " + reply.json()["access_token"]}
            result = {name: measure(client, headers, path, repetitions, concurrency) for name, path in (
                ("analytics", "/api/v1/job-analytics"), ("board", board), ("dashboard", "/api/v1/dashboard"),
            )}
            summary = client.get("/api/v1/job-analytics", headers=headers).json()["summary"]
            assert summary["submitted"] == size
            return {"applications": size, "metrics": result, "analytics_counts": summary}
    finally:
        if account:
            with session_factory().begin() as db:
                db.execute(delete(JobApplication).where(JobApplication.user_id == account))
                db.execute(delete(User).where(User.id == account))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--board", default="/api/v1/job-pipeline")
    parser.add_argument("--repetitions", type=int, default=20)
    parser.add_argument("--concurrency", type=int, default=4)
    parser.add_argument("--queue", action="store_true", help="Measure a local simulated queue, without MySQL or network")
    args = parser.parse_args()
    if args.queue:
        report = queue_benchmark()
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(report))
        return
    settings = get_settings()
    if settings.app_env != "test" or not settings.db_name.endswith("_test"):
        parser.error("Only use a migrated test database")
    if args.repetitions < 1 or not 1 <= args.concurrency <= 8:
        parser.error("Use a positive repetition count and at most eight clients")
    started = datetime.now().astimezone()
    rows = [dataset(size, args.repetitions, args.concurrency, args.board) for size in (0, 250, 1000)]
    report = {"run_at": started.isoformat(), "repetitions": args.repetitions, "concurrency": args.concurrency,
              "board": args.board, "sizes": rows}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps([{"applications": row["applications"], **row["metrics"]} for row in rows]))


def queue_benchmark():
    def trial(concurrency):
        queued = perf_counter()
        done = Event()
        short_wait = None

        class Complete(Exception):
            pass

        def slow(_):
            sleep(0.3)
            return False

        def fast(_):
            nonlocal short_wait
            short_wait = (perf_counter() - queued) * 1000
            done.set()
            return False

        def heartbeat():
            if done.is_set():
                raise Complete
            if perf_counter() - queued > 5:
                raise RuntimeError("Synthetic queue did not finish")

        if concurrency == 1:
            slow(None)
            fast(None)
        else:
            try:
                run_queues(None, (slow, fast), heartbeat, concurrency)
            except Complete:
                pass
        return round(short_wait, 2)

    before = [trial(1) for _ in range(5)]
    after = [trial(2) for _ in range(5)]
    return {"simulated": True, "slow_service_ms": 300, "repetitions": 5,
            "short_wait_ms_serial": before, "short_wait_ms_concurrent": after,
            "short_wait_p50_ms_serial": median(before), "short_wait_p50_ms_concurrent": median(after)}


if __name__ == "__main__":
    main()
