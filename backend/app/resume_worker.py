"""Consume persisted jobs. Run alongside FastAPI with python -m app.resume_worker."""
import argparse
from dataclasses import dataclass
from datetime import timedelta
import logging
from time import sleep
from urllib.parse import urlsplit

from sqlalchemy import select
from sqlalchemy.exc import OperationalError

from app.ai.evidence import approved_text_digest, facts_for_model, redact_blocks, redact_text
from app.ai.evidence import validate_analysis, validate_extraction, validate_optimizations
from app.ai.prompts import ANALYZE, EXTRACT, OPTIMIZE
from app.ai.provider import Provider, provider_fingerprint
from app.core.config import get_settings
from app.core.errors import ApiError
from app.db.session import session_factory
from app.models.resume import Resume, ResumeContent, ResumeJob
from app.models import user  # Register the users table in the standalone worker's ORM metadata.
from app.schemas.career import CareerResult, OptimizationResult, StructuredResume
from app.services.career import store_analysis, store_optimizations
from app.services.resume_parser import PARSER_VERSION, parse_resume
from app.services.resume_storage import storage_path
from app.services.resumes import copy_revision, latest_content, utc_now

logger = logging.getLogger(__name__)
STALE_AFTER = timedelta(minutes=10)

@dataclass(frozen=True)
class Task:
    id: int
    resume_id: int
    kind: str
    attempt: int
    payload: dict

def claim_job(factory) -> Task | None:
    with factory() as db:
        job = db.scalar(select(ResumeJob).where(ResumeJob.state == "queued")
                        .order_by(ResumeJob.id).limit(1).with_for_update(skip_locked=True))
        if job is None:
            return None
        job.state = "running"
        job.started_at = utc_now()
        db.commit()
        return Task(job.id, job.resume_id, job.kind, job.attempt, job.payload)

def find_stale_jobs(factory) -> list[Task]:
    with factory() as db:
        records = db.scalars(select(ResumeJob).where(
            ResumeJob.state == "running", ResumeJob.started_at < utc_now() - STALE_AFTER,
        ).limit(50)).all()
        return [Task(job.id, job.resume_id, job.kind, job.attempt, job.payload) for job in records]

def compute(factory, task: Task, provider_factory):
    with factory() as db:
        resume = db.get(Resume, task.resume_id)
        if resume is None:
            raise ApiError(404, "RESUME_NOT_FOUND", "未找到简历")
        storage_key, file_type = resume.storage_key, resume.file_type
        source = db.get(ResumeContent, task.payload["content_id"]) if task.kind != "parse" else None
    if task.kind == "parse":
        return parse_resume(storage_path(storage_key), file_type)
    if source is None or source.resume_id != task.resume_id:
        raise ApiError(404, "RESUME_CONTENT_NOT_FOUND", "简历内容不存在")

    settings = get_settings()
    if provider_fingerprint(settings) != task.payload["provider"]:
        raise ApiError(409, "MODEL_CONFIG_CHANGED", "模型配置已变化，请重新提交任务")
    blocks = (redact_blocks(source.blocks, task.payload["hidden_blocks"]) if task.kind == "extract"
              else (source.model_blocks or []))
    if (task.payload.get("external_processing_accepted") is not True or not blocks
            or task.payload.get("approved_text_digest") != approved_text_digest(blocks)):
        raise ApiError(422, "EXTERNAL_PROCESSING_CONSENT_REQUIRED", "请重新确认并提交脱敏文本")
    provider = provider_factory(settings)
    try:
        if task.kind == "extract":
            drafts = provider.generate(EXTRACT, {"blocks": blocks}, StructuredResume)
            result, rejected = validate_extraction(drafts, blocks)
            return blocks, result.model_dump(mode="json"), rejected
        payload = {"blocks": blocks, "facts": facts_for_model(source.structured_data or {}),
                   "target_direction": redact_text(task.payload["target_direction"])}
        if task.kind == "analyze":
            result = provider.generate(ANALYZE, payload, CareerResult)
            return validate_analysis(result, blocks)
        if task.kind == "optimize":
            result = provider.generate(OPTIMIZE, payload, OptimizationResult)
            return validate_optimizations(result.suggestions, blocks)
        raise ApiError(500, "UNSUPPORTED_JOB", "任务类型无法处理")
    finally:
        provider.close()

def complete(factory, task: Task, result=None, error_code: str | None = None) -> None:
    with factory() as db:
        resume = db.get(Resume, task.resume_id, with_for_update=True)
        job = db.get(ResumeJob, task.id, with_for_update=True)
        if not resume or not job or job.state != "running" or job.attempt != task.attempt:
            return
        job.finished_at = utc_now()
        job.error_code = error_code
        job.state = "failed" if error_code else "succeeded"
        if error_code:
            if task.kind == "parse":
                resume.parse_status = "failed"
                resume.parse_error = error_code
            db.commit()
            return
        if task.kind == "parse":
            previous = latest_content(db, resume.id, lock=True)
            revision = ResumeContent(resume_id=resume.id, version=(previous.version if previous else 0) + 1,
                                     parser_version=PARSER_VERSION, extracted_text="\n\n".join(block["text"] for block in result),
                                     blocks=result, confirmed=False)
            db.add(revision)
            db.flush()
            job.result_id = revision.id
            resume.parse_status = "parsed"
        elif task.kind == "extract":
            source = db.get(ResumeContent, task.payload["content_id"])
            blocks, structured, rejected = result
            revision = copy_revision(
                db, source, model_blocks=blocks, structured_data=structured, confirmed=False,
                metadata_json={"model": get_settings().llm_model, "prompt_version": EXTRACT.version, "rejected": rejected},
            )
            job.result_id = revision.id
        elif task.kind == "analyze":
            job.result_id = store_analysis(db, resume.user_id, task.payload["content_id"], task.payload["target_direction"],
                                           result, get_settings().llm_model, ANALYZE.version)
        elif task.kind == "optimize":
            job.result_id = store_optimizations(db, task.payload["content_id"], result)
        db.commit()

def run_once(factory=None, provider_factory=Provider) -> bool:
    factory = factory or session_factory()
    for stale in find_stale_jobs(factory):
        complete(factory, stale, error_code="JOB_INTERRUPTED")
    task = claim_job(factory)
    if task is None:
        return False
    try:
        result = compute(factory, task, provider_factory)
        complete(factory, task, result=result)
    except ApiError as exc:
        complete(factory, task, error_code=exc.code)
    except Exception as exc:
        # Never log an exception body that might contain model input or output.
        logger.error("resume task failed id=%s error_type=%s", task.id, type(exc).__name__)
        complete(factory, task, error_code="RESUME_JOB_FAILED")
    return True

def main() -> None:
    from app.services.learning_workflow import run_learning_once
    from app.services.interview_engine import run_interview_once
    from app.services.code_project_workflow import run_code_project_once
    from app.services.discovery_workflow import run_discovery_once
    from app.services.job_workflow import run_job_once
    from app.services.job_strategy_service import run_strategy_once

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--approved-host", help="Require this configured model hostname before the worker starts.")
    parser.add_argument("--strategy-only", action="store_true", help="Process only approved anonymous job strategy reports.")
    args = parser.parse_args()
    if args.approved_host:
        hostname = urlsplit(get_settings().llm_base_url or "").hostname
        if hostname != args.approved_host:
            raise SystemExit("The configured model host does not match the approved destination.")
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    logger.info("resume worker started")
    while True:
        try:
            if args.strategy_only:
                if not run_strategy_once(session_factory()):
                    sleep(1)
                continue
            resume_processed = run_once()
            job_processed = run_job_once(session_factory())
            discovery_processed = run_discovery_once(session_factory())
            code_processed = run_code_project_once(session_factory())
            interview_processed = run_interview_once(session_factory())
            learning_processed = run_learning_once(session_factory())
            strategy_processed = run_strategy_once(session_factory())
            if not any((resume_processed, job_processed, discovery_processed, code_processed, interview_processed,
                        learning_processed, strategy_processed)):
                sleep(1)
        except OperationalError:
            logger.warning("resume worker database temporarily unavailable")
            sleep(3)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
