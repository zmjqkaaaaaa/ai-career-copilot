from datetime import timedelta
import hashlib
import json
import logging
from urllib.parse import urlsplit

from sqlalchemy import select
from app.ai.evidence import redact_text
from app.ai.provider import Provider, model_configured, provider_fingerprint
from app.core.config import get_settings
from app.core.errors import ApiError
from app.models.job import JobAnalysisTask, JobMatch, JobPosition, JobRequirement, JobSkillGap
from app.models.user import User
from app.schemas.job import Advice
from app.services.job_parser import JD_PROMPT, JD_PROMPT_V1, parse_jd
from app.services.llm_monitoring_service import TaskContext, task_provider
from app.services.resumes import utc_now
from app.services.skill_gap_service import ADVICE_FORMAT_ERRORS, ADVICE_PROMPT, ADVICE_PROMPT_V1, fallback_advice

logger = logging.getLogger(__name__)
ACTIVE = ("queued", "running")

def digest(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()

def owned_job(db, user_id, job_id, *, lock=False):
    stmt = select(JobPosition).where(JobPosition.id == job_id, JobPosition.user_id == user_id)
    job = db.scalar(stmt.with_for_update() if lock else stmt)
    if not job:
        raise ApiError(404, "JOB_NOT_FOUND", "未找到岗位")
    return job

def owned_match(db, user_id, match_id):
    match = db.scalar(select(JobMatch).where(JobMatch.id == match_id, JobMatch.user_id == user_id))
    if not match:
        raise ApiError(404, "JOB_MATCH_NOT_FOUND", "未找到匹配报告")
    return match

def active_task(db, job_id):
    return db.scalar(select(JobAnalysisTask).where(JobAnalysisTask.job_id == job_id,
                     JobAnalysisTask.state.in_(ACTIVE)).limit(1).with_for_update())

def rows(db, job):
    return list(db.scalars(select(JobRequirement.requirement).where(
        JobRequirement.job_id == job.id, JobRequirement.revision == job.revision,
    ).order_by(JobRequirement.ordinal)))

def write_requirements(db, job, requirements):
    job.revision += 1
    db.add_all([JobRequirement(job_id=job.id, revision=job.revision, ordinal=index, requirement=requirement)
                for index, requirement in enumerate(requirements)])

def release_job(db, job):
    if active_task(db, job.id):
        raise ApiError(409, "JOB_BUSY", "岗位正在处理，请稍后再试")
    db.delete(job)
    db.commit()

def parse_payload(job):
    if len(job.job_description.strip()) < 10:
        raise ApiError(422, "JD_TEXT_LENGTH", "请先粘贴至少 10 字的 JD")
    return {"job_description": redact_text(job.job_description)}

def advice_payload(match):
    return {"decision": match.score_details["verdict"], "requirements": [
        {"name": redact_text(row["name"]), "dimension": row["dimension"], "importance": row["importance"],
         "status": row["status"], "evidence_status": row["evidence_status"]}
        for row in match.score_details["requirements"]
    ]}

def preview(job, match=None):
    settings = get_settings()
    return {"host": urlsplit(settings.llm_base_url or "").hostname,
            "payload": advice_payload(match) if match else parse_payload(job)}

def enqueue(db, job, match, body, settings):
    if not model_configured(settings):
        raise ApiError(503, "LLM_NOT_CONFIGURED", "请先配置模型服务")
    if not body.accept_external_processing or body.provider_host != urlsplit(settings.llm_base_url).hostname:
        raise ApiError(422, "JOB_CONSENT_REQUIRED", "请核对发送内容和模型地址后提交")
    kind = "recommendations" if match else "parse"
    source = advice_payload(match) if match else parse_payload(job)
    fingerprint = digest([kind, source, match.id if match else None, provider_fingerprint(settings),
                          ADVICE_PROMPT.version if match else JD_PROMPT.version])
    existing = db.scalar(select(JobAnalysisTask).where(JobAnalysisTask.job_id == job.id, JobAnalysisTask.kind == kind,
                                                     JobAnalysisTask.fingerprint == fingerprint).with_for_update())
    if existing and (existing.state != "failed" or not body.retry):
        return existing
    if active_task(db, job.id):
        raise ApiError(409, "JOB_BUSY", "岗位正在处理，请稍后再试")
    recent = db.scalars(select(JobAnalysisTask.attempt).join(JobPosition).where(JobPosition.user_id == job.user_id,
                        JobAnalysisTask.created_at >= utc_now() - timedelta(hours=1)).limit(12)).all()
    if sum(recent) >= 12:
        raise ApiError(429, "JOB_MODEL_LIMIT", "岗位分析已达到每小时额度")
    if existing:
        if existing.attempt >= 3:
            raise ApiError(409, "JOB_RETRY_LIMIT", "已达到此任务的重试上限")
        existing.attempt += 1
        existing.state, existing.error_code, existing.started_at = "queued", None, None
        existing.created_at = utc_now()
        task = existing
    else:
        task = JobAnalysisTask(job_id=job.id, match_id=match.id if match else None, kind=kind, fingerprint=fingerprint,
                               payload={"source": source, "provider": provider_fingerprint(settings), "approved": True,
                                        "prompt_version": ADVICE_PROMPT.version if match else JD_PROMPT.version})
        db.add(task)
    db.flush()
    db.commit()
    return task

def generate_advice(provider, task):
    prompt = ADVICE_PROMPT if task.payload.get("prompt_version") == ADVICE_PROMPT.version else ADVICE_PROMPT_V1
    source = task.payload["source"]
    try:
        return provider.generate(prompt, source, Advice).model_dump(mode="json")
    except ApiError as exc:
        if exc.code not in ADVICE_FORMAT_ERRORS:
            raise
    return provider.generate(ADVICE_PROMPT, source, Advice).model_dump(mode="json")


def run_job_once(factory, provider_factory=Provider):
    with factory() as db:
        stale = db.scalars(select(JobAnalysisTask).where(JobAnalysisTask.state == "running",
                           JobAnalysisTask.started_at < utc_now() - timedelta(minutes=10)).limit(30).with_for_update(skip_locked=True)).all()
        for old in stale:
            old.state, old.error_code = "failed", "JOB_INTERRUPTED"
        task = db.scalar(select(JobAnalysisTask).where(JobAnalysisTask.state == "queued")
                         .order_by(JobAnalysisTask.id).limit(1).with_for_update(skip_locked=True))
        if not task:
            db.commit()
            return False
        task.state, task.started_at = "running", utc_now()
        owner = db.scalar(select(JobPosition.user_id).where(JobPosition.id == task.job_id))
        db.commit()
    result, error = None, None
    jd_prompt = JD_PROMPT if task.payload.get("prompt_version") == JD_PROMPT.version else JD_PROMPT_V1
    try:
        settings = get_settings()
        if not task.payload.get("approved") or task.payload["provider"] != provider_fingerprint(settings):
            raise ApiError(409, "MODEL_CONFIG_CHANGED", "请重新核对发送地址")
        provider = task_provider(provider_factory, settings, factory,
                                 TaskContext("job_matching", owner, task.id, task.attempt, task.created_at, task.started_at))
        try:
            if task.kind == "parse":
                result = parse_jd(provider, task.payload["source"], jd_prompt)
            else:
                result = generate_advice(provider, task)
        finally:
            provider.close()
    except ApiError as exc:
        error = exc.code
    except Exception as exc:
        logger.error("job task %s failed (%s)", task.id, type(exc).__name__)
        error = "JOB_TASK_FAILED"
    with factory() as db:
        job = db.get(JobPosition, task.job_id, with_for_update=True)
        current = db.get(JobAnalysisTask, task.id, with_for_update=True)
        if not job or not current or current.attempt != task.attempt or current.state != "running":
            return True
        if not error and task.kind == "parse":
            requirements = result.pop("requirements")
            job.parsed = {**result, "model": settings.llm_model, "prompt_version": jd_prompt.version}
            job.confirmed = False
            write_requirements(db, job, requirements)
        if task.kind == "recommendations" and (not error or error in ADVICE_FORMAT_ERRORS):
            match = db.get(JobMatch, task.match_id)
            if match and not error:
                match.recommendations = result
            elif match and not match.recommendations:
                match.recommendations = fallback_advice(match.score_details)
        current.state, current.error_code = ("failed" if error else "succeeded"), error
        db.commit()
    return True
