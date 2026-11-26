from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import ApiError
from app.models.career import CareerAnalysis, ResumeOptimization, SkillEvidence, SkillProfile
from app.models.resume import Resume, ResumeContent
from app.schemas.career import AnalysisRead, GroundedCareerResult, OptimizationItem, SKILLS
from app.services.resumes import utc_now

def store_analysis(db: Session, user_id: int, content_id: int, target: str, result: GroundedCareerResult,
                   model: str, prompt_version: str) -> int:
    analysis = CareerAnalysis(user_id=user_id, content_id=content_id, target_direction=target,
                              analysis_result=result.model_dump(mode="json", exclude={"skills"}),
                              model_name=model, prompt_version=prompt_version)
    db.add(analysis)
    db.flush()
    for assessment in result.skills:
        skill = SkillProfile(
            analysis_id=analysis.id, skill_name=assessment.name, skill_category=SKILLS[assessment.name],
            proficiency_level=assessment.level, evidence_status=assessment.status, analysis_reason=assessment.reason,
        )
        db.add(skill)
        db.flush()
        db.add_all([SkillEvidence(skill_profile_id=skill.id, source_type="resume", block_number=source.block_number,
                                  source_content=source.quote) for source in assessment.sources])
    return analysis.id

def analysis_query(user_id: int):
    return (select(CareerAnalysis, ResumeContent.resume_id).join(ResumeContent)
            .join(Resume).where(CareerAnalysis.user_id == user_id, Resume.user_id == user_id,
                                Resume.parse_status != "deleting"))

def analysis_summary(analysis: CareerAnalysis, resume_id: int) -> dict:
    return {**AnalysisRead.model_validate(analysis).model_dump(), "resume_id": resume_id}

def read_analysis(db: Session, user_id: int, analysis_id: int | None, resume_id: int | None) -> dict:
    statement = analysis_query(user_id)
    if analysis_id:
        statement = statement.where(CareerAnalysis.id == analysis_id)
    if resume_id:
        statement = statement.where(ResumeContent.resume_id == resume_id)
    record = db.execute(statement.order_by(CareerAnalysis.id.desc()).limit(1)).first()
    if record is None:
        raise ApiError(404, "CAREER_ANALYSIS_NOT_FOUND", "尚无可查看的职业画像")
    analysis, owner_resume = record
    skills = db.scalars(select(SkillProfile).where(SkillProfile.analysis_id == analysis.id).order_by(SkillProfile.id)).all()
    evidence = db.scalars(select(SkillEvidence).where(SkillEvidence.skill_profile_id.in_([skill.id for skill in skills])).order_by(SkillEvidence.id)).all()
    anchors = {}
    for source in evidence:
        anchors.setdefault(source.skill_profile_id, []).append({"block_number": source.block_number, "quote": source.source_content})
    return {
        "analysis": analysis_summary(analysis, owner_resume),
        "report": {**analysis.analysis_result, "skills": [
            {"name": skill.skill_name, "level": skill.proficiency_level, "status": skill.evidence_status,
             "category": skill.skill_category, "reason": skill.analysis_reason, "sources": anchors.get(skill.id, [])}
            for skill in skills
        ]},
    }

def store_optimizations(db: Session, content_id: int, suggestions: list[OptimizationItem]) -> int | None:
    records = [ResumeOptimization(
        content_id=content_id, original_content=item.original.quote, optimized_content=item.rewritten,
        optimization_reason=item.reason, interview_question=item.interview_question, section=item.section,
        needs_evidence=item.needs_evidence, block_number=item.original.block_number,
    ) for item in suggestions]
    db.add_all(records)
    db.flush()
    return records[0].id if records else None

def optimization_query(resume_id: int):
    return (select(ResumeOptimization).join(ResumeContent)
            .where(ResumeContent.resume_id == resume_id))

def confirm_optimization(db: Session, resume_id: int, record_id: int, text: str) -> ResumeOptimization:
    record = db.scalar(optimization_query(resume_id).where(ResumeOptimization.id == record_id).with_for_update())
    if record is None:
        raise ApiError(404, "OPTIMIZATION_NOT_FOUND", "该优化建议不存在")
    if record.confirmed_at:
        if record.confirmed_text == text:
            return record
        raise ApiError(409, "OPTIMIZATION_ALREADY_CONFIRMED", "该建议已经保存为独立文本版本")
    record.confirmed_text = text
    record.confirmed_at = utc_now()
    db.commit()
    return record
