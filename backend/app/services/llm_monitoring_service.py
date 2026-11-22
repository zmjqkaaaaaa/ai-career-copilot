"""Record model-call metadata without recording submitted content or responses."""
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from functools import partial
import argparse
import json
import logging
from pathlib import Path

from sqlalchemy import case, func, select
from sqlalchemy.exc import SQLAlchemyError

from app.ai.provider import Provider
from app.db.session import session_factory
from app.models.operations import LlmCallMetric
from app.services.resumes import utc_now

logger = logging.getLogger(__name__)
UNITS = Decimal(1_000_000)


@dataclass(frozen=True)
class TaskContext:
    module: str
    user_id: int
    task_id: int
    attempt: int = 1
    created_at: datetime | None = None
    started_at: datetime | None = None


def tokens(value):
    return value if type(value) is int and value >= 0 else None


def record(factory, settings, context, prompt, status, duration_ms, usage):
    pending_ms = None
    if context.attempt == 1 and context.started_at and context.created_at:
        pending_ms = max(0, int((context.started_at - context.created_at).total_seconds() * 1000))
    input_count = tokens(getattr(usage, "prompt_tokens", None))
    output_count = tokens(getattr(usage, "completion_tokens", None))
    price = settings.llm_prices.get(settings.llm_model)
    estimated, currency = None, None
    if price is not None and input_count is not None and output_count is not None:
        estimated = (price.input_per_million * input_count + price.output_per_million * output_count) / UNITS
        currency = price.currency
    try:
        with factory.begin() as db:
            db.add(LlmCallMetric(user_id=context.user_id, task_id=context.task_id, module=context.module,
                                 attempt=context.attempt, model=settings.llm_model, operation=prompt.name,
                                 prompt_version=prompt.version, status=status, duration_ms=duration_ms,
                                 queue_wait_ms=pending_ms, input_tokens=input_count, output_tokens=output_count,
                                 estimated_cost=estimated, currency=currency))
    except SQLAlchemyError as exc:
        logger.warning("model metric unavailable module=%s error=%s", context.module, type(exc).__name__)


def task_provider(provider_factory, settings, factory, context):
    provider = provider_factory(settings)
    if isinstance(provider, Provider):
        provider.metric_sink = partial(record, factory, settings, context)
    return provider


def summary(db, start, end, group, user_id=None):
    metric = LlmCallMetric
    groups = {"module": (metric.module,), "model": (metric.model,), "task": (metric.module, metric.task_id),
              "user": (metric.user_id,), "total": ()}[group]
    queries = (
        select(*groups, metric.currency, func.count().label("calls"),
               func.sum(case((metric.status == "ok", 1), else_=0)).label("successes"),
               func.sum(metric.input_tokens).label("input_tokens"), func.sum(metric.output_tokens).label("output_tokens"),
               func.count(metric.estimated_cost).label("priced_calls"), func.sum(metric.estimated_cost).label("estimated_cost"),
               func.avg(metric.duration_ms).label("mean_duration_ms"),
               func.avg(metric.queue_wait_ms).label("mean_queue_wait_ms"),
               func.sum(case((metric.attempt > 1, 1), else_=0)).label("retry_calls"))
        .where(metric.created_at >= datetime.combine(start, time.min), metric.created_at < datetime.combine(end + timedelta(days=1), time.min))
        .group_by(*groups, metric.currency).order_by(*groups, metric.currency)
    )
    if user_id is not None:
        queries = queries.where(metric.user_id == user_id)
    results = []
    for row in db.execute(queries).mappings():
        data = dict(row)
        cost = data.pop("estimated_cost")
        failed = data["calls"] - int(data["successes"])
        data["successes"], data["retry_calls"] = int(data["successes"]), int(data["retry_calls"])
        for key in ("input_tokens", "output_tokens"):
            data[key] = int(data[key]) if data[key] is not None else None
        for key in ("mean_duration_ms", "mean_queue_wait_ms"):
            data[key] = round(float(data[key]), 2) if data[key] is not None else None
        results.append({**data, "failed": failed, "failure_rate": round(failed / data["calls"], 4),
                        "estimated_cost": str(cost) if cost is not None else None})
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", type=date.fromisoformat, default=utc_now().date() - timedelta(days=7))
    parser.add_argument("--end", type=date.fromisoformat, default=utc_now().date())
    parser.add_argument("--group", choices=("module", "model", "task", "user", "total"), default="module")
    parser.add_argument("--user-id", type=int)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.start > args.end or args.end == date.max or (args.user_id is not None and args.user_id < 1):
        parser.error("Use an ordered date range and a positive user ID")
    with session_factory()() as db:
        rows = summary(db, args.start, args.end, args.group, args.user_id)
    data = json.dumps({"start": args.start.isoformat(), "end": args.end.isoformat(), "group": args.group,
                       "cost_kind": "estimate", "results": rows}, ensure_ascii=True, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(data + "\n", encoding="utf-8")
    else:
        print(data)


if __name__ == "__main__":
    main()
