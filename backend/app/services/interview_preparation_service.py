from sqlalchemy import select

from app.ai.evidence import redact_text
from app.core.errors import ApiError
from app.models.career import CareerAnalysis, SkillEvidence, SkillProfile
from app.models.code_project import CodeProject, ProjectSnapshot
from app.models.discovery import DiscoverySession, ProductPrd, ProjectRecommendation
from app.models.job import JobPosition, JobRequirement
from app.models.resume import Resume, ResumeContent
from app.models.user_profile import UserProfile
from app.services.codebase_parser import mask_source
from app.services.code_project_workflow import mastery
from app.services.career_context import application_match, matching_report, scoped_recommendations
from app.services.application_tracking_service import owned as owned_application
from app.services.interview_schedule_service import owned_schedule
from app.services.resume_version_service import owned_version
from app.services.interview_modes import DIFFICULTIES, MODES, STAGES, STYLES, schedule
from app.services.project_knowledge_service import citations, files_for


def clean(text, limit=650):
    return redact_text(mask_source(str(text)))[:limit]


def selected_application(db, user_id, application_id, schedule_id):
    appointment = owned_schedule(db, user_id, schedule_id) if schedule_id else None
    if appointment and application_id and application_id != appointment.application_id:
        raise ApiError(422, "CAREER_CONTEXT_MISMATCH", "面试日程与所选投递不一致")
    identifier = appointment.application_id if appointment else application_id
    return (owned_application(db, user_id, identifier) if identifier else None), appointment


def available(db, user_id, application_id=None, schedule_id=None):
    application, _ = selected_application(db, user_id, application_id, schedule_id)
    resumes = db.execute(select(ResumeContent, Resume.original_filename).join(Resume).where(
        Resume.user_id == user_id, ResumeContent.confirmed.is_(True), Resume.parse_status != "deleting"
    ).order_by(ResumeContent.id.desc()).limit(40))
    jobs = db.scalars(select(JobPosition).where(JobPosition.user_id == user_id).order_by(JobPosition.id.desc()).limit(30))
    plans_query = select(ProjectRecommendation).where(ProjectRecommendation.user_id == user_id).order_by(ProjectRecommendation.id.desc())
    if application:
        match = application_match(db, user_id, application)
        plans_query = scoped_recommendations(user_id, match.id, application.id) if match else plans_query.where(False)
    plans = db.scalars(plans_query.where(ProjectRecommendation.selected.is_(True)).limit(20)).all()
    repo_query = select(CodeProject).where(CodeProject.user_id == user_id, CodeProject.active_commit.is_not(None))
    if application:
        repo_query = repo_query.where(CodeProject.recommendation_id.in_([plan.id for plan in plans]))
    repos = db.scalars(repo_query.order_by(CodeProject.id.desc()).limit(20))
    profile = db.scalar(select(UserProfile).where(UserProfile.user_id == user_id))
    return {
        "target": application.snapshot["position"] if application else (profile.target_position if profile and profile.target_position else "AI 产品经理"),
        "modes": {key: value[0] for key, value in MODES.items()}, "styles": STYLES, "difficulties": DIFFICULTIES,
        "stages": STAGES,
        "resumes": [{"id": content.id, "label": name, "version": content.version} for content, name in resumes],
        "jobs": [{"id": row.id, "label": row.position_name, "version": row.revision} for row in jobs],
        "projects": [{"id": row.id, "label": row.data.get("name", "已选项目")} for row in plans],
        "repositories": [{"id": row.id, "label": row.slug, "active_commit": row.active_commit,
                          "versions": list(db.scalars(select(ProjectSnapshot.commit_sha).where(
                              ProjectSnapshot.project_id == row.id).order_by(ProjectSnapshot.id.desc()).limit(30)))}
                         for row in repos],
    }


def pick(db, stmt, model, identifier):
    if identifier:
        stmt = stmt.where(model.id == identifier)
    record = db.scalar(stmt.order_by(model.id.desc()).limit(1))
    if identifier and record is None:
        raise ApiError(404, "INTERVIEW_SOURCE_UNAVAILABLE", "选定资料不可用或未确认")
    return record


def project_sources(db, user_id, setup, *, targeted, match, application):
    repositories = select(CodeProject).where(CodeProject.user_id == user_id, CodeProject.active_commit.is_not(None))
    plans = select(ProjectRecommendation).where(ProjectRecommendation.user_id == user_id,
                                               ProjectRecommendation.selected.is_(True))
    if not targeted:
        repo = pick(db, repositories, CodeProject, setup.repository_id)
        linked = db.scalar(plans.where(ProjectRecommendation.id == repo.recommendation_id)) if repo and repo.recommendation_id else None
        return repo, linked if linked and not setup.recommendation_id else pick(db, plans, ProjectRecommendation, setup.recommendation_id)

    chosen_repo = pick(db, repositories, CodeProject, setup.repository_id) if setup.repository_id else None
    linked_id = chosen_repo.recommendation_id if chosen_repo else None
    if application and chosen_repo and not linked_id:
        raise ApiError(422, "CAREER_CONTEXT_MISMATCH", "请选择已关联到本次投递项目方案的仓库")
    if setup.recommendation_id and linked_id and setup.recommendation_id != linked_id:
        raise ApiError(422, "CAREER_CONTEXT_MISMATCH", "所选仓库与项目方案不一致")
    plan_id = setup.recommendation_id or linked_id
    scoped = scoped_recommendations(user_id, match.id, application.id if application else None) if match else None
    if plan_id:
        plan = pick(db, plans, ProjectRecommendation, plan_id)
        source = db.get(DiscoverySession, plan.session_id)
        bound = scoped is not None and db.scalar(scoped.where(ProjectRecommendation.id == plan_id)) is not None
        if not bound and (application is not None or source.source_snapshot is not None):
            raise ApiError(422, "CAREER_CONTEXT_MISMATCH", "所选项目不属于当前岗位与投递的匹配报告")
    elif scoped is not None:
        plan = db.scalar(scoped.where(ProjectRecommendation.selected.is_(True)).limit(1))
    else:
        plan = None
    repo = chosen_repo
    if not repo and plan:
        repo = pick(db, repositories.where(CodeProject.recommendation_id == plan.id), CodeProject, None)
    return repo, plan


def build_context(db, user_id, setup):
    profile = db.scalar(select(UserProfile).where(UserProfile.user_id == user_id))
    application, appointment = selected_application(db, user_id, setup.application_id, setup.interview_schedule_id)
    version = owned_version(db, user_id, application.resume_version_id) if application and application.resume_version_id else None
    job = pick(db, select(JobPosition).where(JobPosition.user_id == user_id), JobPosition,
               setup.job_id) if application is None else None
    if application:
        match = application_match(db, user_id, application)
    elif job:
        match = matching_report(db, user_id, job.id, job.revision, content_id=setup.resume_content_id)
    else:
        match = None
    requested_resume = setup.resume_content_id or (match.content_id if match and not application else None)
    resume = pick(db, select(ResumeContent).join(Resume).where(Resume.user_id == user_id,
                  ResumeContent.confirmed.is_(True), Resume.parse_status != "deleting"), ResumeContent,
                  requested_resume) if not application and (requested_resume or not setup.job_id) else None
    repo, plan = project_sources(db, user_id, setup, targeted=bool(application or setup.job_id), match=match, application=application)
    if setup.mode == "resume" and resume is None and version is None:
        raise ApiError(422, "INTERVIEW_RESUME_REQUIRED", "简历深度模式需要一份已确认简历")

    facts, provenance = [], {}
    def add(kind, text, **source):
        if text:
            entry = {"id": f"{kind}:{sum(item['kind'] == kind for item in facts) + 1}", "kind": kind, "text": clean(text), **source}
            facts.append(entry)

    if profile:
        for field in ("undergraduate_major", "graduate_major", "undergraduate_degree", "skills", "interested_industries"):
            value = getattr(profile, field)
            if value:
                add("profile", f"{field} · {', '.join(value[:8]) if isinstance(value, list) else value}")
        for field in ("internship_experience", "project_experience"):
            for item in (getattr(profile, field) or [])[:2]:
                add("profile", f"本人档案填报 · {item.get('title', '')}")
    if resume:
        provenance["resume"] = {"id": resume.resume_id, "content_id": resume.id, "version": resume.version}
        for block in (resume.model_blocks if resume.model_blocks is not None else resume.blocks or [])[:8]:
            add("resume", block.get("text"), block=block.get("number"), version=resume.version)
        analysis = db.scalar(select(CareerAnalysis).where(CareerAnalysis.user_id == user_id,
                             CareerAnalysis.content_id == resume.id).order_by(CareerAnalysis.id.desc()).limit(1))
        if analysis:
            provenance["analysis_id"] = analysis.id
            skills = db.execute(select(SkillProfile, SkillEvidence).outerjoin(SkillEvidence).where(
                SkillProfile.analysis_id == analysis.id).order_by(SkillProfile.id).limit(12))
            for skill, evidence in skills:
                add("ability", f"{skill.skill_name} · {skill.evidence_status} · {evidence.source_content if evidence else ''}",
                    status=skill.evidence_status)
    if application:
        provenance["application"] = {"id": application.id}
        if appointment:
            provenance["application"]["schedule_id"] = appointment.id
        source = application.snapshot
        revision = source["job_revision"]
        provenance["job"] = {"id": application.job_id, "revision": revision, "confirmed": bool(source["requirements"])}
        add("jd", source["jd"], revision=revision, status="raw")
        for requirement in source["requirements"][:7]:
            add("jd", requirement["name"], revision=revision, status="confirmed")
        if version:
            provenance["resume_version"] = {"id": version.id, "version": version.version_number}
            for block in [item for item in version.content if item.get("training_text")][:8]:
                add("resume", block["training_text"], block=block["number"], version=version.version_number)
    if job:
        provenance["job"] = {"id": job.id, "revision": job.revision, "confirmed": job.confirmed}
        requirements = list(db.scalars(select(JobRequirement).where(JobRequirement.job_id == job.id,
                            JobRequirement.revision == job.revision).order_by(JobRequirement.ordinal).limit(8)))
        if job.confirmed and requirements:
            for row in requirements:
                add("jd", row.requirement.get("name"), revision=job.revision, status="confirmed")
        else:
            add("jd", job.job_description, revision=job.revision, status="raw")
    if match:
        provenance["job"]["match_id"] = match.id
        if match.analysis_id:
            provenance["analysis_id"] = match.analysis_id
        for item in match.score_details.get("hard_flags", [])[:3]:
            add("gap", item.get("name"), status="assessment")
    if plan:
        provenance["plan"] = {"recommendation_id": plan.id}
        add("plan", "拟议项目 · " + str(plan.data.get("name", "")) + " · " + str(plan.data.get("positioning", "")))
        prd = db.scalar(select(ProductPrd).where(ProductPrd.recommendation_id == plan.id, ProductPrd.user_id == user_id)
                        .order_by(ProductPrd.version.desc()).limit(1))
        if prd:
            provenance["plan"].update(prd_id=prd.id, version=prd.version)
            add("plan", prd.content, version=prd.version, status="draft")
    if repo:
        sha = setup.commit or repo.active_commit
        snapshot = db.scalar(select(ProjectSnapshot).where(ProjectSnapshot.project_id == repo.id, ProjectSnapshot.commit_sha == sha))
        if snapshot is None:
            raise ApiError(404, "INTERVIEW_SNAPSHOT_UNAVAILABLE", "找不到所选项目版本")
        provenance["repository"] = {"id": repo.id, "commit": sha, "slug": repo.slug}
        for row in citations(files_for(db, snapshot.id, loaded=True), limit=6):
            # Keep precise line boundaries when a source must fit the per-fragment budget.
            lines = []
            for line in row["code"].split("\n"):
                if sum(len(item) + 1 for item in lines) + len(line) > 620:
                    break
                lines.append(line)
            if lines:
                add("code", "\n".join(lines), path=row["path"], start=row["start"], end=row["start"] + len(lines) - 1,
                    symbol=row["symbol"], commit=sha)
        report = mastery(db, snapshot)
        for row in report["dimensions"]:
            if row["attempts"]:
                add("practice", f"{row['label']} · {row['status']} · {row['attempts']} 次练习", status=row["status"])
    job_target = application.snapshot["position"] if application else (job.position_name if job else None)
    target = job_target if application else setup.target or job_target or (profile.target_position if profile else None) or "AI 产品经理"
    return {"target": clean(target, 150), "refs": facts, "sources": provenance,
            "schedule": schedule(setup.model_dump())}
