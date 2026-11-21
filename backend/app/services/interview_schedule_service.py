from datetime import timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import select

from app.core.errors import ApiError
from app.models.application import InterviewSchedule
from app.models.user import User
from app.services.application_tracking_service import check_revision, naive_utc, owned
from app.services.job_workflow import digest


def owned_schedule(db, user_id, identifier, lock=False):
    stmt = select(InterviewSchedule).where(InterviewSchedule.user_id == user_id, InterviewSchedule.id == identifier)
    row = db.scalar(stmt.with_for_update() if lock else stmt)
    if row is None:
        raise ApiError(404, "INTERVIEW_SCHEDULE_NOT_FOUND", "未找到面试日程")
    return row


def save(db, user_id, body, identifier=None):
    db.get(User, user_id, with_for_update=True)
    stmt = select(InterviewSchedule).where(InterviewSchedule.user_id == user_id)
    if identifier is None:
        key = str(body.request_id)
        signature = digest(body.model_dump(mode="json"))
        existing = db.scalar(stmt.where(InterviewSchedule.request_id == key).with_for_update())
        if existing:
            if existing.fingerprint != signature:
                raise ApiError(409, "REQUEST_CHANGED", "此请求编号已被其他内容使用")
            return existing
        application = owned(db, user_id, body.application_id, lock=True)
        row = InterviewSchedule(user_id=user_id, application_id=application.id, request_id=key, fingerprint=signature)
        db.add(row)
    else:
        row = owned_schedule(db, user_id, identifier, lock=True)
        check_revision(row, body.revision)
        row.revision += 1
    try:
        zone = ZoneInfo(body.timezone)
    except (ZoneInfoNotFoundError, ValueError):
        raise ApiError(422, "INTERVIEW_TIMEZONE_INVALID", "请选择有效的 IANA 时区") from None
    if body.scheduled_at.utcoffset() != body.scheduled_at.astimezone(zone).utcoffset():
        raise ApiError(422, "INTERVIEW_TIMEZONE_MISMATCH", "面试时间偏移与所选时区不一致")
    start = naive_utc(body.scheduled_at)
    try:
        end = start + timedelta(minutes=body.duration)
    except OverflowError:
        raise ApiError(422, "INTERVIEW_TIME_INVALID", "面试结束时间超出可用范围") from None
    if body.result != "cancelled":
        overlapping = stmt.where(InterviewSchedule.scheduled_at < end, InterviewSchedule.ends_at > start,
                                 InterviewSchedule.details["result"].as_string() != "cancelled")
        if identifier is not None:
            overlapping = overlapping.where(InterviewSchedule.id != identifier)
        with db.no_autoflush:
            if db.scalar(overlapping.limit(1).with_for_update()):
                raise ApiError(409, "INTERVIEW_TIME_CONFLICT", "该时间与已有面试重叠")
    row.scheduled_at, row.ends_at, row.timezone = start, end, body.timezone
    row.details = body.model_dump(mode="json", exclude={
        "request_id", "application_id", "revision", "scheduled_at", "timezone"
    })
    db.commit()
    return row
