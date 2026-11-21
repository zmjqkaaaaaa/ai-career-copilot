import hmac
from datetime import timedelta
from hashlib import sha256
from time import time
from urllib.parse import urlsplit

from sqlalchemy import func, select

from app.ai.job_strategy_prompts import STRATEGY_PROMPT
from app.ai.provider import Provider, model_configured, provider_fingerprint
from app.core.config import get_settings
from app.core.errors import ApiError
from app.models.application import JobStrategyReport
from app.models.user import User
from app.schemas.application import StrategyResult
from app.services.job_pipeline_service import analytics
from app.services.job_workflow import digest
from app.services.resumes import utc_now


def model_data(stats):
    # Drop free text and raw identifiers before any external processing.
    return {key: stats[key] for key in ("start", "end", "summary", "minimum_sample", "sample_insufficient")} | {
        key: [{k: v for k, v in row.items() if k not in {"label", "id"}} | {"group": i}
              for i, row in enumerate(sorted(stats[key], key=lambda item: -item["valid"])[:8], 1)]
        for key in ("by_position", "by_resume")
    }


def sign(settings, user_id, stats, expires):
    content = digest(["job-strategy", user_id, stats, provider_fingerprint(settings), expires, STRATEGY_PROMPT.version])
    return f"{expires}." + hmac.new(settings.jwt_secret.get_secret_value().encode(), content.encode(), sha256).hexdigest()


def preview(db, user_id, body, settings):
    if not model_configured(settings):
        raise ApiError(503, "LLM_NOT_CONFIGURED", "请先配置模型服务")
    stats = analytics(db, user_id, body)
    return {"payload": model_data(stats), "approval": sign(settings, user_id, stats, int(time()) + 600),
            "host": urlsplit(settings.llm_base_url).hostname}


def enqueue(db, user_id, body, settings):
    if not model_configured(settings):
        raise ApiError(503, "LLM_NOT_CONFIGURED", "请先配置模型服务")
    db.get(User, user_id, with_for_update=True)
    stats = analytics(db, user_id, body)
    expires = int(body.approval.split(".")[0])
    if expires < time() or not hmac.compare_digest(body.approval, sign(settings, user_id, stats, expires)):
        raise ApiError(409, "STRATEGY_PREVIEW_CHANGED", "统计或模型配置已改变，请重新预览")
    provider = provider_fingerprint(settings)
    signature = digest([stats, provider, STRATEGY_PROMPT.version])
    existing = db.scalar(select(JobStrategyReport).where(
        JobStrategyReport.user_id == user_id, JobStrategyReport.fingerprint == signature
    ).with_for_update())
    if existing and existing.state != "failed":
        return existing
    count = db.scalar(select(func.count()).select_from(JobStrategyReport).where(
        JobStrategyReport.user_id == user_id, JobStrategyReport.updated_at >= utc_now() - timedelta(hours=1)
    ))
    if count >= 6:
        raise ApiError(429, "STRATEGY_RATE_LIMIT", "已达到策略分析的每小时额度，请稍后再试")
    if existing:
        existing.state, existing.error_code, existing.started_at = "queued", None, None
        existing.updated_at = utc_now()
        row = existing
    else:
        row = JobStrategyReport(user_id=user_id, fingerprint=signature, statistics=stats, provider_key=provider,
                                model_name=settings.llm_model, prompt_version=STRATEGY_PROMPT.version)
        db.add(row)
    db.commit()
    return row


def run_strategy_once(factory, provider_factory=Provider, *, report_id=None):
    settings = get_settings()
    with factory() as db:
        stale = db.scalars(select(JobStrategyReport).where(
            JobStrategyReport.state == "running", JobStrategyReport.started_at < utc_now() - timedelta(minutes=10)
        ).limit(30).with_for_update(skip_locked=True))
        for row in stale:
            row.state, row.error_code = "failed", "STRATEGY_INTERRUPTED"
        queued = select(JobStrategyReport).where(JobStrategyReport.state == "queued")
        if report_id is not None:
            queued = queued.where(JobStrategyReport.id == report_id)
        task = db.scalar(queued.order_by(JobStrategyReport.id).limit(1).with_for_update(skip_locked=True))
        if task is None:
            db.commit()
            return False
        task.state, task.started_at = "running", utc_now().replace(microsecond=0)
        db.flush()
        identifier, provider_key, stats, started = task.id, task.provider_key, task.statistics, task.started_at
        db.commit()
    output, error = None, None
    service = None
    try:
        if not model_configured(settings) or provider_key != provider_fingerprint(settings):
            raise ApiError(409, "MODEL_CONFIG_CHANGED", "模型配置已改变")
        service = provider_factory(settings)
        data = service.generate(STRATEGY_PROMPT, model_data(stats), StrategyResult)
        output = data.model_dump()
        if stats["sample_insufficient"]:
            output["inferences"] = []
            output["observations"] = ["有效投递样本不足，暂不判断简历质量或比较转化表现。"]
    except ApiError as exc:
        error = exc.code
    except Exception:
        error = "STRATEGY_MODEL_ERROR"
    finally:
        if service:
            service.close()
    with factory() as db:
        task = db.get(JobStrategyReport, identifier, with_for_update=True)
        if task and task.state == "running" and task.started_at == started:
            task.state, task.analysis, task.error_code = ("failed" if error else "succeeded"), output, error
            db.commit()
    return True
