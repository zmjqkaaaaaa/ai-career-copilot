from datetime import date

from fastapi import APIRouter, Query
from sqlalchemy import select

from app.api.dependencies import AppSettings, CurrentUser, Database
from app.core.errors import ApiError
from app.models.application import ApplicationStatusHistory, InterviewSchedule, JobApplication, JobStrategyReport, ResumeVersion
from app.models.user_profile import UserProfile
from app.schemas.application import (
    ApplicationCreate, ApplicationPatch, Period, ResumeSelection, ResumeVersionCreate, ResumeVersionInput,
    ScheduleCreate, SchedulePatch, Status, StatusUpdate, StrategyRequest,
)
from app.services import application_tracking_service as tracking
from app.services import interview_schedule_service as schedules
from app.services import job_pipeline_service as pipeline
from app.services import job_strategy_service as strategy
from app.services import resume_version_service as versions
from app.services.resumes import utc_now

router = APIRouter(tags=["job applications"])


def fields(row, names):
    return {key: getattr(row, key) for key in names.split()}


def version_view(row, full=True):
    data = fields(row, "id original_resume_id content_id target_job_id job_revision target_position version_name "
                       "version_number previous_id series_id change_summary")
    return {**data, "created_at": tracking.stamp(row.created_at), **({"content": row.content} if full else {})}


def application_view(row, full=False):
    data = fields(row, "id job_id resume_version_id current_status revision channel valid_submission")
    snapshot = row.snapshot if full else {key: value for key, value in row.snapshot.items() if key not in {"jd", "requirements"}}
    return {**data, **row.metadata_json, "job": snapshot,
            "applied_at": tracking.stamp(row.applied_at), "updated_at": tracking.stamp(row.updated_at)}


def schedule_view(row, application):
    return {**fields(row, "id application_id timezone revision"), **row.details,
            "company": application.snapshot["company"], "position": application.snapshot["position"],
            "scheduled_at": tracking.stamp(row.scheduled_at), "ends_at": tracking.stamp(row.ends_at)}


def strategy_view(row):
    return {**fields(row, "id state statistics analysis error_code model_name prompt_version"),
            "created_at": tracking.stamp(row.created_at)}


@router.post("/resume-versions/preview")
def resume_preview(body: ResumeSelection, user: CurrentUser, db: Database):
    return versions.preview(db, user.id, body)


@router.post("/resume-versions", status_code=201)
def create_version(body: ResumeVersionCreate, user: CurrentUser, db: Database):
    return version_view(versions.save(db, user.id, body, body.content_id, body.target_job_id))


@router.get("/resume-versions")
def list_versions(user: CurrentUser, db: Database, offset: int = Query(0, ge=0)):
    stmt = select(ResumeVersion).where(ResumeVersion.user_id == user.id).order_by(ResumeVersion.id.desc())
    return [version_view(row, full=False) for row in db.scalars(stmt.offset(offset).limit(100))]


@router.get("/resume-versions/{version_id}")
def get_version(version_id: int, user: CurrentUser, db: Database):
    return version_view(versions.owned_version(db, user.id, version_id))


@router.patch("/resume-versions/{version_id}", status_code=201)
def revise_version(version_id: int, body: ResumeVersionInput, user: CurrentUser, db: Database):
    previous = versions.owned_version(db, user.id, version_id)
    return version_view(versions.save(db, user.id, body, previous.content_id, previous.target_job_id, previous))


@router.post("/applications", status_code=201)
def create_application(body: ApplicationCreate, user: CurrentUser, db: Database):
    return application_view(tracking.create(db, user.id, body), full=True)


@router.get("/applications")
def list_applications(user: CurrentUser, db: Database, status: Status | None = None,
                      offset: int = Query(0, ge=0)):
    stmt = pipeline.application_query(user.id)
    if status is not None:
        stmt = stmt.where(JobApplication.current_status == status)
    return [application_view(row) for row in db.scalars(stmt.order_by(JobApplication.id.desc()).offset(offset).limit(100))]


@router.get("/applications/{application_id}")
def get_application(application_id: int, user: CurrentUser, db: Database):
    return application_view(tracking.owned(db, user.id, application_id), full=True)


@router.patch("/applications/{application_id}")
def update_application(application_id: int, body: ApplicationPatch, user: CurrentUser, db: Database):
    return application_view(tracking.edit(db, user.id, application_id, body), full=True)


@router.post("/applications/{application_id}/status")
def update_status(application_id: int, body: StatusUpdate, user: CurrentUser, db: Database):
    return application_view(tracking.move(db, user.id, application_id, body))


@router.get("/applications/{application_id}/history")
def application_history(application_id: int, user: CurrentUser, db: Database):
    row = tracking.owned(db, user.id, application_id)
    stmt = select(ApplicationStatusHistory).where(ApplicationStatusHistory.application_id == row.id).order_by(
        ApplicationStatusHistory.id.desc())
    return [{**fields(event, "id previous_status new_status notes"), "changed_at": tracking.stamp(event.changed_at)}
            for event in db.scalars(stmt)]


@router.post("/interview-schedules", status_code=201)
def create_schedule(body: ScheduleCreate, user: CurrentUser, db: Database):
    row = schedules.save(db, user.id, body)
    return schedule_view(row, tracking.owned(db, user.id, row.application_id))


@router.get("/interview-schedules")
def list_schedules(user: CurrentUser, db: Database, offset: int = Query(0, ge=0)):
    data = db.execute(select(InterviewSchedule, JobApplication).join(JobApplication).where(
        InterviewSchedule.user_id == user.id, JobApplication.user_id == user.id
    ).order_by(InterviewSchedule.scheduled_at.desc(), InterviewSchedule.id.desc()).offset(offset).limit(100))
    return [schedule_view(row, application) for row, application in data]


@router.patch("/interview-schedules/{schedule_id}")
def edit_schedule(schedule_id: int, body: SchedulePatch, user: CurrentUser, db: Database):
    row = schedules.save(db, user.id, body, schedule_id)
    return schedule_view(row, tracking.owned(db, user.id, row.application_id))


@router.get("/job-pipeline")
def get_pipeline(user: CurrentUser, db: Database):
    columns = {status: [] for status in tracking.STATUSES}
    for row in db.scalars(pipeline.application_query(user.id).order_by(JobApplication.updated_at.desc())):
        columns[row.current_status].append(application_view(row))
    profile = db.scalar(select(UserProfile).where(UserProfile.user_id == user.id))
    upcoming = db.execute(select(InterviewSchedule, JobApplication).join(JobApplication).where(
        InterviewSchedule.user_id == user.id, JobApplication.user_id == user.id,
        InterviewSchedule.scheduled_at >= utc_now(), InterviewSchedule.details["result"].as_string() == "scheduled"
    ).order_by(InterviewSchedule.scheduled_at).limit(5))
    return {"target": profile.target_position if profile else None, "columns": columns,
            "upcoming": [schedule_view(row, app) for row, app in upcoming]}


@router.get("/job-analytics")
def get_analytics(user: CurrentUser, db: Database, start: date | None = None, end: date | None = None):
    return pipeline.analytics(db, user.id, Period(start=start, end=end))


@router.post("/job-strategy/preview")
def preview_strategy(body: Period, user: CurrentUser, db: Database, settings: AppSettings):
    return strategy.preview(db, user.id, body, settings)


@router.post("/job-strategy/analyze", status_code=202)
def analyze_strategy(body: StrategyRequest, user: CurrentUser, db: Database, settings: AppSettings):
    return strategy_view(strategy.enqueue(db, user.id, body, settings))


@router.get("/job-strategy/reports")
def list_strategy(user: CurrentUser, db: Database):
    stmt = select(JobStrategyReport).where(JobStrategyReport.user_id == user.id)
    return [strategy_view(row) for row in db.scalars(stmt.order_by(JobStrategyReport.id.desc()).limit(20))]


@router.get("/job-strategy/reports/{report_id}")
def get_strategy(report_id: int, user: CurrentUser, db: Database):
    row = db.scalar(select(JobStrategyReport).where(JobStrategyReport.user_id == user.id,
                                                    JobStrategyReport.id == report_id))
    if row is None:
        raise ApiError(404, "STRATEGY_REPORT_NOT_FOUND", "未找到求职策略分析")
    return strategy_view(row)
