from sqlalchemy import select

from app.core.errors import ApiError
from app.models.application import ResumeVersion
from app.models.career import ResumeOptimization
from app.models.job import JobMatch
from app.models.resume import Resume, ResumeContent
from app.models.user import User
from app.services.job_workflow import digest, owned_job


def owned_version(db, user_id, identifier):
    row = db.scalar(select(ResumeVersion).where(ResumeVersion.id == identifier, ResumeVersion.user_id == user_id))
    if row is None:
        raise ApiError(404, "RESUME_VERSION_NOT_FOUND", "未找到简历版本")
    return row


def sources(db, user_id, content_id, target_job_id):
    content = db.scalar(select(ResumeContent).join(Resume).where(
        ResumeContent.id == content_id, Resume.user_id == user_id, ResumeContent.confirmed.is_(True),
        Resume.parse_status != "deleting",
    ))
    if content is None:
        raise ApiError(404, "CONFIRMED_RESUME_NOT_FOUND", "请选择自己的已确认简历")
    job = owned_job(db, user_id, target_job_id) if target_job_id else None
    optimizations = list(db.scalars(select(ResumeOptimization).where(
        ResumeOptimization.content_id == content.id, ResumeOptimization.confirmed_text.is_not(None),
        ResumeOptimization.confirmed_at.is_not(None), ResumeOptimization.needs_evidence.is_(False),
    ).order_by(ResumeOptimization.id)))
    return content, job, optimizations


def preview(db, user_id, body):
    content, job, optimizations = sources(db, user_id, body.content_id, body.target_job_id)
    match = db.scalar(select(JobMatch).where(
        JobMatch.user_id == user_id, JobMatch.job_id == job.id, JobMatch.revision == job.revision,
        JobMatch.content_id == content.id,
    ).order_by(JobMatch.id.desc()).limit(1)) if job else None
    return {"blocks": content.blocks, "optimizations": [
        {"id": row.id, "number": row.block_number, "text": row.confirmed_text, "reason": row.optimization_reason}
        for row in optimizations
    ], "recommendations": match.recommendations if match else None,
        "gaps": [item["name"] for item in match.score_details["requirements"] if item["status"] != "matched"] if match else []}


def save(db, user_id, body, content_id, target_job_id, previous=None):
    db.get(User, user_id, with_for_update=True)
    key = str(body.request_id)
    signature = digest([body.model_dump(mode="json"), previous.id if previous else None])
    existing = db.scalar(select(ResumeVersion).where(
        ResumeVersion.user_id == user_id, ResumeVersion.request_id == key
    ).with_for_update())
    if existing is not None:
        if existing.fingerprint != signature:
            raise ApiError(409, "REQUEST_CHANGED", "此请求编号已被其他内容使用")
        return existing
    if previous and db.scalar(select(ResumeVersion.id).where(ResumeVersion.user_id == user_id,
            ResumeVersion.series_id == previous.series_id, ResumeVersion.version_number > previous.version_number
            ).limit(1).with_for_update()):
        raise ApiError(409, "RESUME_VERSION_STALE", "请从此简历系列的最新版本继续修改")

    content, job, choices = sources(db, user_id, content_id, target_job_id)
    blocks = {block["number"]: block for block in content.blocks}
    if len(set(body.block_numbers)) != len(body.block_numbers) or any(n not in blocks for n in body.block_numbers):
        raise ApiError(422, "RESUME_BLOCK_INVALID", "请选择不重复且有原文依据的简历段落")
    available = {row.id: row for row in choices}
    replacements = {}
    for identifier in body.optimization_ids:
        item = available.get(identifier)
        if item is None or item.block_number not in body.block_numbers or item.block_number in replacements:
            raise ApiError(422, "RESUME_OPTIMIZATION_INVALID", "请选择已确认且对应所选段落的优化内容")
        replacements[item.block_number] = item
    snapshot = []
    visible_for_model = {block["number"]: block["text"] for block in content.model_blocks} if content.model_blocks is not None else {
        number: block["text"] for number, block in blocks.items()
    }
    for number in body.block_numbers:
        item = replacements.get(number)
        training_text = visible_for_model.get(number)
        if item and training_text:
            training_text = item.confirmed_text
        snapshot.append({"number": number, "text": item.confirmed_text if item else blocks[number]["text"],
                         "optimization_id": item.id if item else None, "training_text": training_text})
    row = ResumeVersion(user_id=user_id, request_id=key, fingerprint=signature,
                        series_id=previous.series_id if previous else key,
                        version_number=previous.version_number + 1 if previous else 1,
                        previous_id=previous.id if previous else None, original_resume_id=content.resume_id,
                        content_id=content.id, target_job_id=job.id if job else None,
                        job_revision=job.revision if job else None,
                        target_position=job.position_name if job else None, version_name=body.version_name,
                        change_summary=body.change_summary, content=snapshot)
    db.add(row)
    db.commit()
    return row
