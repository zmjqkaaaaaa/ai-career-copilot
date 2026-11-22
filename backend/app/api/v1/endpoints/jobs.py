from datetime import date
from typing import Annotated

from fastapi import APIRouter, File, UploadFile
from sqlalchemy import select
from tempfile import TemporaryDirectory
from pathlib import Path

from app.api.dependencies import AppSettings, CurrentUser, Database
from app.core.errors import ApiError
from app.core.job_scoring import VERSION
from app.models.job import JobAnalysisTask, JobMatch, JobPosition, JobSkillGap
from app.models.resume import Resume, ResumeContent
from app.models.user import User
from app.schemas.application import JobImport, JobPatch
from app.schemas.job import JobCreate, MatchRequest, ModelRequest, RequirementEdit
from app.services.job_matching_service import candidate, score
from app.services import job_discovery_service as discovery
from app.services.job_parser import grounded_requirements
from app.services.job_workflow import active_task, digest, enqueue, owned_job, owned_match, preview, release_job, rows, write_requirements
from app.services.resume_parser import parse_resume
from app.services.skill_gap_service import enrich

router = APIRouter(tags=["job matching"])

def view(record, fields):
    return {name: getattr(record, name) for name in fields.split()}

def job_view(job):
    return view(job, "id position_name company_name location job_type salary_range source_url job_description parsed revision confirmed created_at favorite archived discovery_metadata")

def match_view(match):
    return view(match, "id job_id content_id analysis_id revision scoring_version overall_score evidence_coverage score_details recommendations created_at")

def task_view(task):
    return view(task, "id job_id match_id kind state attempt error_code")

@router.post("/jobs/import", status_code=200)
def import_jd(file: Annotated[UploadFile, File()], _user: CurrentUser, settings: AppSettings):
    kind = Path(file.filename or "").suffix.lower().removeprefix(".")
    if kind not in {"txt", "pdf", "docx"}:
        raise ApiError(415, "JOB_FILE_TYPE", "请选择 TXT、PDF 或 DOCX")
    data = file.file.read(2 * 1024 * 1024 + 1)
    if len(data) > 2 * 1024 * 1024:
        raise ApiError(413, "JOB_FILE_TOO_LARGE", "岗位文件最多 2 MB")
    if kind == "txt":
        try:
            result = data.decode("utf-8-sig")
        except UnicodeDecodeError:
            raise ApiError(422, "JOB_FILE_ENCODING", "请使用 UTF-8 编码的 TXT") from None
    else:
        directory = settings.resume_storage_dir.parent
        directory.mkdir(parents=True, exist_ok=True)
        with TemporaryDirectory(dir=directory, prefix="jd-") as temporary:
            file_path = Path(temporary) / f"job.{kind}"
            file_path.write_bytes(data)
            result = "\n\n".join(block["text"] for block in parse_resume(file_path, kind))
    if not 10 <= len(result.strip()) <= 12000:
        raise ApiError(422, "JD_TEXT_LENGTH", "JD 文本须为 10 到 12000 字符")
    return {"job_description": result.strip()}

@router.get("/jobs/candidate-versions")
def candidate_versions(user: CurrentUser, db: Database):
    data = db.execute(select(ResumeContent.id, ResumeContent.version, Resume.original_filename).join(Resume).where(
        Resume.user_id == user.id, ResumeContent.confirmed.is_(True), Resume.parse_status != "deleting",
    ).order_by(ResumeContent.id.desc()).limit(50))
    return [dict(row._mapping) for row in data]

@router.post("/jobs", status_code=201)
def create(body: JobCreate, user: CurrentUser, db: Database):
    return job_view(discovery.capture(db, user.id, body))

@router.post("/jobs/import-jd", status_code=201)
def capture_jd(body: JobImport, user: CurrentUser, db: Database):
    metadata = body.metadata.model_dump(mode="json") if body.metadata else None
    return job_view(discovery.capture(db, user.id, body, metadata))

@router.get("/jobs")
def list_jobs(user: CurrentUser, db: Database, offset: int = 0, q: str | None = None,
              company: str | None = None, title: str | None = None, city: str | None = None,
              industry: str | None = None, education: str | None = None, skill: str | None = None,
              published_from: date | None = None, published_to: date | None = None,
              favorite: bool | None = None, include_archived: bool = False):
    stmt = discovery.search(user.id, q, company, title, city, industry, education, skill,
                            published_from, published_to, favorite, include_archived)
    latest = select(JobMatch.overall_score).where(
        JobMatch.job_id == JobPosition.id, JobMatch.user_id == user.id, JobMatch.revision == JobPosition.revision
    ).order_by(JobMatch.id.desc()).limit(1).scalar_subquery()
    result = []
    for job, score_value in db.execute(stmt.add_columns(latest).order_by(JobPosition.id.desc()).offset(max(0, offset)).limit(50)):
        result.append({**job_view(job), "latest_score": score_value})
    return result

@router.patch("/jobs/{job_id}")
def patch_job(job_id: int, body: JobPatch, user: CurrentUser, db: Database):
    return job_view(discovery.update(db, user.id, job_id, body))

@router.get("/jobs/{job_id}")
def detail(job_id: int, user: CurrentUser, db: Database):
    job = owned_job(db, user.id, job_id)
    tasks = db.scalars(select(JobAnalysisTask).where(JobAnalysisTask.job_id == job.id).order_by(JobAnalysisTask.id.desc()).limit(20)).all()
    return {**job_view(job), "requirements": rows(db, job), "tasks": [task_view(task) for task in tasks]}

@router.delete("/jobs/{job_id}", status_code=204)
def remove(job_id: int, user: CurrentUser, db: Database):
    db.get(User, user.id, with_for_update=True)
    job = owned_job(db, user.id, job_id, lock=True)
    if discovery.has_applications(db, job):
        job.archived = True
        db.commit()
        return
    release_job(db, job)

@router.get("/jobs/{job_id}/parse-preview")
def parse_preview(job_id: int, user: CurrentUser, db: Database):
    return preview(owned_job(db, user.id, job_id))

@router.post("/jobs/{job_id}/parse", status_code=202)
def parse(job_id: int, body: ModelRequest, user: CurrentUser, db: Database, settings: AppSettings):
    db.get(User, user.id, with_for_update=True)
    return task_view(enqueue(db, owned_job(db, user.id, job_id, lock=True), None, body, settings))

@router.put("/jobs/{job_id}/requirements")
def confirm(job_id: int, body: RequirementEdit, user: CurrentUser, db: Database):
    job = owned_job(db, user.id, job_id, lock=True)
    if not job.revision or job.revision != body.revision or active_task(db, job.id):
        raise ApiError(409, "JOB_REVISION_CHANGED", "岗位版本已变更或正在处理，请刷新")
    requirements = [item.model_dump() for item in grounded_requirements(body.requirements, job.job_description, editing=True)]
    if not job.confirmed or requirements != rows(db, job):
        write_requirements(db, job, requirements)
    job.confirmed = True
    db.commit()
    return {**job_view(job), "requirements": requirements}

@router.post("/jobs/{job_id}/match")
def create_match(job_id: int, body: MatchRequest, user: CurrentUser, db: Database):
    job = owned_job(db, user.id, job_id, lock=True)
    if not job.confirmed or job.revision != body.revision:
        raise ApiError(409, "JOB_REQUIREMENTS_UNCONFIRMED", "请先核对并确认当前岗位要求")
    requirements = rows(db, job)
    if any(index < 0 or index >= len(requirements) for index in body.assessments):
        raise ApiError(422, "JOB_REQUIREMENT_INVALID", "岗位要求序号无效")
    person = candidate(db, user.id, body.content_id, body.analysis_id)
    fingerprint = digest([VERSION, job.revision, body.content_id, person, body.assessments])
    existing = db.scalar(select(JobMatch).where(JobMatch.job_id == job.id, JobMatch.fingerprint == fingerprint).with_for_update())
    if existing:
        return match_view(existing)
    report = score(requirements, person, body.assessments)
    match = JobMatch(user_id=user.id, job_id=job.id, content_id=body.content_id, analysis_id=person["analysis_id"],
                     revision=job.revision, scoring_version=VERSION, fingerprint=fingerprint, score_details=report,
                     overall_score=report["overall_score"], evidence_coverage=report["evidence_coverage"])
    db.add(match)
    db.flush()
    db.add_all([JobSkillGap(match_id=match.id, result=enrich(row)) for row in report["requirements"] if row["status"] != "matched"])
    db.refresh(match)
    db.commit()
    return match_view(match)

@router.get("/jobs/{job_id}/match")
def get_match(job_id: int, user: CurrentUser, db: Database):
    owned_job(db, user.id, job_id)
    result = db.scalar(select(JobMatch).where(JobMatch.job_id == job_id, JobMatch.user_id == user.id).order_by(JobMatch.id.desc()).limit(1))
    if not result:
        raise ApiError(404, "JOB_MATCH_NOT_FOUND", "尚未生成匹配报告")
    return match_view(result)

@router.get("/job-matches")
def history(user: CurrentUser, db: Database, offset: int = 0):
    records = db.execute(select(JobMatch, JobPosition.position_name).join(JobPosition).where(
        JobMatch.user_id == user.id, JobPosition.user_id == user.id,
    ).order_by(JobMatch.id.desc()).offset(max(0, offset)).limit(50))
    return [{**match_view(match), "position_name": title} for match, title in records]

@router.get("/job-matches/{match_id}/gaps")
def gaps(match_id: int, user: CurrentUser, db: Database):
    owned_match(db, user.id, match_id)
    return list(db.scalars(select(JobSkillGap.result).where(JobSkillGap.match_id == match_id).order_by(JobSkillGap.id)))

@router.get("/job-matches/{match_id}")
def read_match(match_id: int, user: CurrentUser, db: Database):
    return match_view(owned_match(db, user.id, match_id))

@router.get("/job-matches/{match_id}/recommendations-preview")
def advice_preview(match_id: int, user: CurrentUser, db: Database):
    match = owned_match(db, user.id, match_id)
    return preview(None, match)

@router.post("/job-matches/{match_id}/recommendations", status_code=202)
def advice(match_id: int, body: ModelRequest, user: CurrentUser, db: Database, settings: AppSettings):
    db.get(User, user.id, with_for_update=True)
    match = owned_match(db, user.id, match_id)
    return task_view(enqueue(db, owned_job(db, user.id, match.job_id, lock=True), match, body, settings))

@router.get("/job-analysis-tasks/{task_id}")
def task_progress(task_id: int, user: CurrentUser, db: Database):
    task = db.scalar(select(JobAnalysisTask).join(JobPosition).where(
        JobAnalysisTask.id == task_id, JobPosition.user_id == user.id,
    ))
    if not task:
        raise ApiError(404, "JOB_TASK_NOT_FOUND", "未找到岗位分析任务")
    return task_view(task)
