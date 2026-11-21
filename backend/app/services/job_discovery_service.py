from sqlalchemy import and_, func, or_, select

from app.core.errors import ApiError
from app.models.application import JobApplication
from app.models.job import JobPosition
from app.models.user import User
from app.services.job_workflow import active_task, owned_job


def reject_duplicate(db, user_id, values, exclude=None):
    same_content = (
        func.lower(JobPosition.position_name) == values["position_name"].casefold(),
        func.lower(func.coalesce(JobPosition.company_name, "")) == (values["company_name"] or "").casefold(),
        func.lower(func.coalesce(JobPosition.location, "")) == (values["location"] or "").casefold(),
        JobPosition.job_description == values["job_description"],
    )
    identity = and_(*same_content)
    if values["source_url"]:
        identity = or_(identity, JobPosition.source_url == values["source_url"])
    stmt = select(JobPosition.id).where(JobPosition.user_id == user_id, identity)
    if exclude is not None:
        stmt = stmt.where(JobPosition.id != exclude)
    if db.scalar(stmt.limit(1).with_for_update()) is not None:
        raise ApiError(409, "JOB_DUPLICATE", "此岗位已录入，请在岗位列表中查找")


def capture(db, user_id, body, metadata=None):
    db.get(User, user_id, with_for_update=True)
    values = body.model_dump(mode="json", exclude={"metadata"})
    reject_duplicate(db, user_id, values)
    job = JobPosition(user_id=user_id, **values, discovery_metadata=metadata)
    db.add(job)
    db.commit()
    return job


def update(db, user_id, job_id, body):
    db.get(User, user_id, with_for_update=True)
    job = owned_job(db, user_id, job_id, lock=True)
    if body.job:
        if active_task(db, job.id):
            raise ApiError(409, "JOB_BUSY", "岗位正在处理，请稍后再试")
        values = body.job.model_dump(mode="json")
        reject_duplicate(db, user_id, values, exclude=job.id)
        if job.job_description != values["job_description"]:
            job.revision += 1
            job.parsed, job.confirmed = None, False
        for key, value in values.items():
            setattr(job, key, value)
    if body.favorite is not None:
        job.favorite = body.favorite
    if body.metadata is not None:
        job.discovery_metadata = body.metadata.model_dump(mode="json")
    db.commit()
    return job


def has_applications(db, job):
    return db.scalar(select(JobApplication.id).where(
        JobApplication.user_id == job.user_id, JobApplication.job_id == job.id
    ).limit(1).with_for_update()) is not None


def search(user_id, q=None, company=None, title=None, city=None, industry=None, education=None,
           skill=None, published_from=None, published_to=None, favorite=None, include_archived=False):
    stmt = select(JobPosition).where(JobPosition.user_id == user_id)
    metadata = JobPosition.discovery_metadata
    if not include_archived:
        stmt = stmt.where(JobPosition.archived.is_(False))
    if q:
        stmt = stmt.where(or_(*(column.contains(q, autoescape=True) for column in (
            JobPosition.company_name, JobPosition.position_name, JobPosition.job_description
        ))))
    for value, column in ((company, JobPosition.company_name), (title, JobPosition.position_name),
                          (city, JobPosition.location), (industry, metadata["industry"].as_string()),
                          (education, metadata["education"].as_string())):
        if value:
            stmt = stmt.where(column.contains(value, autoescape=True))
    if skill:
        stmt = stmt.where(or_(metadata["skills"].as_string().contains(skill, autoescape=True),
                              JobPosition.job_description.contains(skill, autoescape=True)))
    published = metadata["published_at"].as_string()
    if published_from:
        stmt = stmt.where(published >= published_from.isoformat(), published != "null")
    if published_to:
        stmt = stmt.where(published <= published_to.isoformat(), published != "null")
    if favorite is not None:
        stmt = stmt.where(JobPosition.favorite.is_(favorite))
    return stmt
