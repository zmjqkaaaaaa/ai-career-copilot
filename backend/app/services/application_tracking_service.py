from datetime import UTC

from sqlalchemy import select

from app.core.errors import ApiError
from app.models.application import ApplicationStatusHistory, JobApplication
from app.models.user import User
from app.services.career_context import application_match
from app.services.job_workflow import digest, owned_job, rows
from app.services.resume_version_service import owned_version
from app.services.resumes import utc_now

STATUSES = ("wishlist", "applied", "written_test", "interview_1", "interview_2",
            "hr_interview", "offer", "rejected", "withdrawn")
METADATA = ("notes", "next_action", "contact", "feedback", "rejection_reason")


def naive_utc(value):
    return value.astimezone(UTC).replace(tzinfo=None) if value is not None else None


def stamp(value):
    return value.replace(tzinfo=UTC) if value is not None else None


def owned(db, user_id, identifier, lock=False):
    stmt = select(JobApplication).where(JobApplication.id == identifier, JobApplication.user_id == user_id)
    row = db.scalar(stmt.with_for_update() if lock else stmt)
    if row is None:
        raise ApiError(404, "APPLICATION_NOT_FOUND", "未找到投递记录")
    return row


def check_revision(row, revision):
    if row.revision != revision:
        raise ApiError(409, "REVISION_CHANGED", "数据已更新，请刷新后重试")


def snapshot(db, job):
    return {"company": job.company_name, "position": job.position_name, "job_type": job.job_type,
            "industry": (job.discovery_metadata or {}).get("industry"), "location": job.location,
            "source_url": job.source_url, "jd": job.job_description, "job_revision": job.revision,
            "requirements": rows(db, job) if job.confirmed else []}


def validate_version(db, row, version_id):
    if version_id is None:
        return
    version = owned_version(db, row.user_id, version_id)
    if version.target_job_id not in (None, row.job_id):
        raise ApiError(422, "RESUME_VERSION_JOB_MISMATCH", "请选择此岗位对应的简历版本")


def pin_match(db, row, match_id=None):
    selected = application_match(db, row.user_id, row, match_id)
    row.snapshot = {**row.snapshot, "match_id": selected.id if selected else None}


def validate_date(value, preserve=None):
    when = naive_utc(value)
    if when and when > utc_now():
        raise ApiError(422, "APPLICATION_FUTURE_DATE", "投递时间不能晚于现在")
    return when or preserve


def append_status(db, row, key, previous, note=None):
    db.add(ApplicationStatusHistory(application_id=row.id, request_id=key, previous_status=previous,
                                    new_status=row.current_status, notes=note))


def create(db, user_id, body):
    db.get(User, user_id, with_for_update=True)
    key = str(body.request_id)
    signature = digest(body.model_dump(mode="json", exclude={"job_match_id"} if body.job_match_id is None else None))
    stmt = select(JobApplication).where(JobApplication.user_id == user_id)
    existing = db.scalar(stmt.where(JobApplication.request_id == key).with_for_update())
    if existing:
        if existing.fingerprint != signature:
            raise ApiError(409, "REQUEST_CHANGED", "此请求编号已被其他内容使用")
        return existing
    job = owned_job(db, user_id, body.job_id, lock=True)
    if job.archived:
        raise ApiError(409, "JOB_ARCHIVED", "已归档岗位不能新建投递")
    if db.scalar(stmt.where(JobApplication.job_id == job.id).with_for_update()):
        raise ApiError(409, "APPLICATION_DUPLICATE", "已存在此岗位的投递记录")
    sent_at = validate_date(body.applied_at)
    row = JobApplication(user_id=user_id, job_id=job.id, request_id=key, fingerprint=signature,
                         snapshot=snapshot(db, job), metadata_json=body.model_dump(include=set(METADATA)),
                         resume_version_id=body.resume_version_id, channel=body.channel,
                         applied_at=sent_at, current_status="applied" if sent_at else "wishlist",
                         valid_submission=body.valid_submission)
    validate_version(db, row, body.resume_version_id)
    pin_match(db, row, body.job_match_id)
    db.add(row)
    db.flush()
    append_status(db, row, key, None)
    db.commit()
    return row


def edit(db, user_id, identifier, body):
    row = owned(db, user_id, identifier, lock=True)
    check_revision(row, body.revision)
    updates = body.model_dump(exclude_unset=True, exclude={"revision"})
    if "resume_version_id" in updates and updates["resume_version_id"] != row.resume_version_id:
        if row.applied_at and row.resume_version_id is not None:
            raise ApiError(409, "APPLICATION_RESUME_FROZEN", "该投递已绑定发出时的简历版本")
        validate_version(db, row, updates["resume_version_id"])
        row.resume_version_id = updates["resume_version_id"]
        row.snapshot = {**row.snapshot, "match_id": None}
        pin_match(db, row)
    if "applied_at" in updates:
        if row.applied_at is None:
            raise ApiError(422, "APPLICATION_STATUS_REQUIRED", "请通过状态变更记录已投递")
        row.applied_at = validate_date(updates["applied_at"], row.applied_at)
    for field in ("channel", "valid_submission"):
        if field in updates:
            setattr(row, field, updates[field])
    row.metadata_json = {**row.metadata_json, **{key: updates[key] for key in METADATA if key in updates}}
    row.revision += 1
    db.commit()
    return row


def move(db, user_id, identifier, body):
    db.get(User, user_id, with_for_update=True)
    row = owned(db, user_id, identifier, lock=True)
    key = str(body.request_id)
    existing = db.scalar(select(ApplicationStatusHistory).where(
        ApplicationStatusHistory.application_id == identifier, ApplicationStatusHistory.request_id == key
    ))
    if existing:
        if existing.new_status != body.status or existing.notes != body.notes:
            raise ApiError(409, "REQUEST_CHANGED", "此请求编号已被其他内容使用")
        return row
    check_revision(row, body.revision)
    previous = row.current_status
    if previous == body.status:
        return row
    if body.status == "wishlist" and row.applied_at:
        raise ApiError(409, "APPLICATION_ALREADY_SENT", "已投递记录不能退回待投递，可记录后续进度或撤回")
    if body.status in STATUSES[1:7] and row.applied_at is None:
        row.applied_at = validate_date(body.applied_at, utc_now())
        if row.snapshot.get("match_id") is None:
            row.snapshot = snapshot(db, owned_job(db, user_id, row.job_id, lock=True))
            pin_match(db, row)
    row.current_status = body.status
    row.revision += 1
    append_status(db, row, key, previous, body.notes)
    db.commit()
    return row
