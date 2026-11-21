from datetime import timedelta
import hashlib
import json
from urllib.parse import urlsplit

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.evidence import approved_text_digest, redact_blocks
from app.ai.prompts import ANALYZE, EXTRACT, OPTIMIZE
from app.ai.provider import model_configured, provider_fingerprint
from app.core.config import Settings
from app.core.errors import ApiError
from app.models.resume import Resume, ResumeJob
from app.models.user import User
from app.schemas.career import AnalyzeRequest, ExtractTrigger, OptimizeRequest, ParseTrigger
from app.services.resume_parser import PARSER_VERSION
from app.services.resumes import ACTIVE_STATES, active_job, latest_content, owned_resume, require_content, utc_now

PROMPTS = {"extract": EXTRACT, "analyze": ANALYZE, "optimize": OPTIMIZE}
MAX_AI_REQUESTS = 12
MAX_ATTEMPTS = 3
AI_WINDOW = timedelta(hours=1)

def start_job(db: Session, user_id: int, resume_id: int, kind: str,
              body: ParseTrigger | ExtractTrigger | AnalyzeRequest | OptimizeRequest, settings: Settings) -> ResumeJob:
    # A per-account lock also serializes quotas across different resumes.
    db.get(User, user_id, with_for_update=True)
    resume = owned_resume(db, user_id, resume_id, lock=True)
    running = active_job(db, resume.id)
    if kind == "parse":
        content = latest_content(db, resume.id, lock=True)
        generation = content.id if body.reparse and content is not None else None
        payload = {"parser_version": PARSER_VERSION, "base_content_id": generation}
    else:
        if not body.accept_external_processing:
            raise ApiError(422, "EXTERNAL_PROCESSING_CONSENT_REQUIRED", "请先确认允许发送本次脱敏文本")
        if not model_configured(settings):
            raise ApiError(503, "LLM_NOT_CONFIGURED", "请先配置模型服务")
        if body.provider_host != urlsplit(settings.llm_base_url).hostname:
            raise ApiError(409, "MODEL_DESTINATION_CHANGED", "模型服务地址已变化，请刷新核对后重新提交")
        content = require_content(db, resume.id, body.content_id)
        payload = {"content_id": content.id, "prompt_version": PROMPTS[kind].version, "provider": provider_fingerprint(settings)}
        if kind == "extract":
            if content.structured_data is not None:
                raise ApiError(409, "PARSE_REQUIRED", "重新提取前请先重新解析原文件")
            hidden = sorted(set(body.hidden_blocks))
            model_blocks = redact_blocks(content.blocks, hidden)
            if not model_blocks:
                raise ApiError(422, "EMPTY_MODEL_INPUT", "请至少保留一个可供解析的简历段落")
            payload["hidden_blocks"] = hidden
        else:
            if not content.confirmed:
                raise ApiError(409, "CONFIRMED_CONTENT_REQUIRED", "请先确认简历提取结果")
            payload["target_direction"] = body.target_direction
            model_blocks = content.model_blocks or []
        payload["approved_text_digest"] = approved_text_digest(model_blocks)
        payload["external_processing_accepted"] = True
    dedupe_key = hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    existing = db.scalar(select(ResumeJob).where(ResumeJob.resume_id == resume.id, ResumeJob.kind == kind,
                                                 ResumeJob.dedupe_key == dedupe_key).with_for_update())
    retryable = existing is not None and existing.state == "failed" and body.retry
    if existing and not retryable:
        return existing
    if running is not None:
        raise ApiError(409, "RESUME_BUSY", "这份简历已有处理任务，请稍后再试")
    if kind == "extract" and latest_content(db, resume.id, lock=True).id != content.id:
        raise ApiError(409, "RESUME_VERSION_CHANGED", "内容已有新版本，请刷新后继续")
    if kind != "parse":
        attempts = db.scalars(select(ResumeJob.attempt).join(Resume).where(
            Resume.user_id == user_id, ResumeJob.kind.in_(tuple(PROMPTS)),
            ResumeJob.scheduled_at > utc_now() - AI_WINDOW,
        ).limit(MAX_AI_REQUESTS).with_for_update()).all()
        if sum(attempts) >= MAX_AI_REQUESTS:
            raise ApiError(429, "AI_REQUEST_LIMIT", "当前账号的模型调用已达每小时上限，请稍后重试")
    if existing:
        if existing.attempt >= MAX_ATTEMPTS:
            raise ApiError(409, "JOB_RETRY_LIMIT", "此任务已达到重试上限，请检查配置或重新解析")
        existing.attempt += 1
        existing.state = "queued"
        existing.scheduled_at = utc_now()
        existing.started_at = existing.finished_at = existing.error_code = None
        job = existing
    else:
        job = ResumeJob(resume_id=resume.id, kind=kind, dedupe_key=dedupe_key, payload=payload)
        db.add(job)
    if kind == "parse":
        resume.parse_status = "queued"
        resume.parse_error = None
    db.flush()
    db.commit()
    return job

def job_history(db: Session, resume_id: int) -> list[ResumeJob]:
    return list(db.scalars(select(ResumeJob).where(ResumeJob.resume_id == resume_id).order_by(ResumeJob.id.desc()).limit(20)))
