from sqlalchemy import or_, select

from app.core.errors import ApiError
from app.models.discovery import DiscoverySession, ProjectRecommendation
from app.models.job import JobMatch, JobPosition
from app.services.job_workflow import owned_match
from app.services.resume_version_service import owned_version


def matching_report(db, user_id, job_id, revision, *, content_id=None, match_id=None, filter_content=False):
    stmt = select(JobMatch).where(JobMatch.user_id == user_id, JobMatch.job_id == job_id, JobMatch.revision == revision)
    if filter_content or content_id is not None:
        stmt = stmt.where(JobMatch.content_id == content_id)
    if match_id is not None:
        chosen = owned_match(db, user_id, match_id)
        if db.scalar(stmt.where(JobMatch.id == chosen.id)) is None:
            raise ApiError(422, "CAREER_CONTEXT_MISMATCH", "匹配报告与所选岗位、JD 版本或简历版本不一致")
        return chosen
    return db.scalar(stmt.order_by(JobMatch.id.desc()).limit(1))


def application_match(db, user_id, application, match_id=None):
    version = owned_version(db, user_id, application.resume_version_id) if application.resume_version_id else None
    pinned = application.snapshot.get("match_id")
    if match_id is not None and pinned is not None and pinned != match_id:
        raise ApiError(422, "CAREER_CONTEXT_MISMATCH", "请使用此投递已固定的匹配报告")
    if pinned is not None and match_id is None:
        return db.scalar(select(JobMatch).where(JobMatch.user_id == user_id, JobMatch.id == pinned,
                                               JobMatch.job_id == application.job_id))
    return matching_report(db, user_id, application.job_id, application.snapshot["job_revision"],
                           content_id=version.content_id if version else None, match_id=match_id,
                           filter_content=version is not None)


def discovery_binding(db, user_id, match_id=None, application_id=None):
    if application_id is not None:
        from app.services.application_tracking_service import owned as owned_application
        application = owned_application(db, user_id, application_id, lock=True)
        match = application_match(db, user_id, application, match_id)
        result = binding_view(match, application.snapshot["position"], application.id)
        if application.snapshot.get("match_id") is None:
            application.snapshot = {**application.snapshot, "match_id": result["match_id"]}
            application.revision += 1
        return result
    if match_id is None:
        return None
    match = owned_match(db, user_id, match_id)
    title = db.scalar(select(JobPosition.position_name).where(
        JobPosition.id == match.job_id, JobPosition.user_id == user_id
    ))
    if title is None:
        raise ApiError(404, "JOB_NOT_FOUND", "未找到岗位")
    return binding_view(match, title, None)


def binding_view(match, title, application_id):
    if match is None:
        raise ApiError(409, "CAREER_MATCH_REQUIRED", "请先为此投递关联的岗位和简历版本生成匹配报告")
    return {"job_id": match.job_id, "match_id": match.id, "revision": match.revision, "role": title,
            "application_id": application_id, "content_id": match.content_id, "analysis_id": match.analysis_id,
            "score": match.overall_score,
            "gaps": [row["name"] for row in match.score_details.get("hard_flags", [])][:8]}


def scoped_recommendations(user_id, match_id, application_id):
    return select(ProjectRecommendation).join(DiscoverySession).where(
        ProjectRecommendation.user_id == user_id, DiscoverySession.user_id == user_id,
        DiscoverySession.job_match_id == match_id,
        or_(DiscoverySession.application_id.is_(None), DiscoverySession.application_id == application_id),
    ).order_by(DiscoverySession.application_id.is_not(None).desc(), ProjectRecommendation.id.desc())
