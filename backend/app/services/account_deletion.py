import logging
from datetime import timedelta

from sqlalchemy import delete, select

from app.core.errors import ApiError
from app.core.security import password_hasher
from app.models.application import JobApplication, JobStrategyReport, ResumeVersion
from app.models.career import CareerAnalysis
from app.models.code_project import CodeProject, ProjectTask
from app.models.discovery import DiscoveryTask
from app.models.interview import InterviewSession, InterviewTask
from app.models.job import JobAnalysisTask, JobPosition
from app.models.learning import LearningJob
from app.models.operations import PendingFileDeletion
from app.models.resume import Resume, ResumeJob
from app.models.user import User
from app.services.resume_storage import storage_path
from app.services.resumes import utc_now

logger = logging.getLogger(__name__)


def ensure_idle(db, user_id):
    # Lock existing queued work before deletion so a Worker can't claim it mid-transaction.
    tasks = (
        (ResumeJob, Resume, ResumeJob.resume_id == Resume.id),
        (JobAnalysisTask, JobPosition, JobAnalysisTask.job_id == JobPosition.id),
        (ProjectTask, CodeProject, ProjectTask.project_id == CodeProject.id),
        (InterviewTask, InterviewSession, InterviewTask.session_id == InterviewSession.id),
    )
    queries = [select(task.state).join(owner, link).where(
        owner.user_id == user_id, task.state.in_(("queued", "running"))
    ) for task, owner, link in tasks]
    queries.extend(select(task.state).where(task.user_id == user_id, task.state.in_(("queued", "running")))
                   for task in (DiscoveryTask, LearningJob, JobStrategyReport))
    for query in queries:
        if "running" in db.scalars(query.with_for_update()).all():
            raise ApiError(409, "ACCOUNT_TASK_RUNNING", "还有正在执行的任务，请稍后重试删除")


def delete_account(db, user_id, password):
    user = db.get(User, user_id, with_for_update=True, populate_existing=True)
    if user is None or not user.is_active or not password_hasher.verify(password, user.password_hash):
        raise ApiError(403, "ACCOUNT_PASSWORD_INVALID", "密码验证失败")
    ensure_idle(db, user_id)
    keys = db.scalars(select(Resume.storage_key).where(Resume.user_id == user_id).with_for_update()).all()
    for key in keys:
        db.merge(PendingFileDeletion(storage_key=key))
    # Remove restrictive children before MySQL cascades the account-owned records.
    for model in (JobApplication, ResumeVersion, CareerAnalysis, Resume):
        db.execute(delete(model).where(model.user_id == user_id))
    db.delete(user)
    db.commit()


def clean_file_once(factory):
    with factory.begin() as db:
        now = utc_now()
        row = db.scalar(select(PendingFileDeletion).where(PendingFileDeletion.next_attempt_at <= now)
                        .order_by(PendingFileDeletion.next_attempt_at, PendingFileDeletion.storage_key)
                        .limit(1).with_for_update(skip_locked=True))
        if row is None:
            return False
        try:
            storage_path(row.storage_key).unlink(missing_ok=True)
        except OSError as exc:
            row.attempts += 1
            row.next_attempt_at = now + timedelta(seconds=min(3600, 10 * 2 ** min(row.attempts, 9)))
            logger.warning("account file cleanup deferred type=%s", type(exc).__name__)
        else:
            db.delete(row)
    return True
