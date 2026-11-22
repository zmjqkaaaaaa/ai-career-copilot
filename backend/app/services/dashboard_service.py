from datetime import date

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.models.application import JobApplication
from app.models.discovery import DiscoverySession, ProjectRecommendation
from app.models.interview import InterviewReport, InterviewSession
from app.models.job import JobMatch, JobPosition, JobSkillGap
from app.models.learning import LearningTask
from app.models.user_profile import UserProfile
from app.services.job_pipeline_service import actions_query
from app.services.learning_plan import diagnosis, latest

OPEN_TASK_STATES = ("pending", "in_progress", "needs_revision")


def current_match(db: Session, user_id: int):
    entry = db.execute(
        select(JobMatch.id, JobPosition.id.label("job_id"), JobPosition.position_name)
        .join(JobPosition, JobMatch.job_id == JobPosition.id)
        .where(JobMatch.user_id == user_id, JobPosition.user_id == user_id, JobPosition.archived.is_(False),
               JobMatch.revision == JobPosition.revision)
        .order_by(JobMatch.id.desc()).limit(1)
    ).first()
    if entry is None:
        return None
    gaps = db.scalars(select(JobSkillGap.result).where(JobSkillGap.match_id == entry.id)
                      .order_by(JobSkillGap.id).limit(4))
    return {"id": entry.id, "job_id": entry.job_id, "position": entry.position_name,
            "gaps": [{"name": item["name"], "status": item["status"]} for item in gaps]}


def latest_interview(db: Session, user_id: int):
    entry = db.execute(
        select(InterviewReport.data, InterviewSession.id, InterviewSession.target)
        .join(InterviewSession).where(InterviewSession.user_id == user_id)
        .order_by(InterviewReport.id.desc()).limit(1)
    ).first()
    if entry is None:
        return None
    weakness = next((row["knowledge_point"] for row in entry.data.get("weaknesses", [])
                     if row.get("knowledge_point")), None)
    return {"session_id": entry.id, "target": entry.target, "score": entry.data.get("score"),
            "answered": entry.data["answered"], "weakness": weakness}


def next_action(saved_action, tasks, interview, match, target):
    if saved_action:
        return {"kind": "application", "text": saved_action.metadata_json["next_action"],
                "application_id": saved_action.id}
    pending = next((task for task in tasks if task["status"] in OPEN_TASK_STATES), None)
    if pending:
        return {"kind": "learning", "text": f"完成今日任务「{pending['title']}」"}
    if interview and interview["weakness"]:
        return {"kind": "interview", "text": f"复盘面试薄弱项「{interview['weakness']}」"}
    if match and match["gaps"]:
        return {"kind": "matching", "text": f"核对岗位要求「{match['gaps'][0]['name']}」"}
    if not target:
        return {"kind": "profile", "text": "在个人档案中填写目标岗位"}
    if not match:
        return {"kind": "matching", "text": "添加一份目标岗位 JD，开始岗位匹配"}
    return {"kind": "exploration", "text": "从岗位要求出发，探索一个可以实践的项目"}


def snapshot(db: Session, user_id: int, day: date) -> dict:
    profile = latest(db, UserProfile, user_id)
    job = db.scalar(select(JobPosition).where(JobPosition.user_id == user_id, JobPosition.archived.is_(False))
                    .order_by(JobPosition.id.desc()).limit(1))
    target = (profile.target_position if profile else None) or (job.position_name if job else None)
    match = current_match(db, user_id)
    projects = db.scalars(
        select(ProjectRecommendation).join(DiscoverySession)
        .where(ProjectRecommendation.user_id == user_id, DiscoverySession.user_id == user_id)
        .order_by(ProjectRecommendation.selected.desc(), ProjectRecommendation.id.desc()).limit(3)
    )
    today = db.scalars(
        select(LearningTask).where(LearningTask.user_id == user_id, LearningTask.due == day.isoformat())
        .order_by(case((LearningTask.status.in_(OPEN_TASK_STATES), 0), else_=1), LearningTask.id).limit(5)
    )
    tasks = [{"id": row.id, "title": row.data["title"], "minutes": row.data["minutes"], "status": row.status}
             for row in today]
    interview = latest_interview(db, user_id)
    counts = dict(db.execute(select(JobApplication.current_status, func.count()).where(
        JobApplication.user_id == user_id
    ).group_by(JobApplication.current_status)).all())
    action = db.scalar(actions_query(user_id).limit(1))
    return {"day": day, "target_position": target, "profile_complete": profile is not None,
            "skills": diagnosis(db, user_id)["summary"], "match": match,
            "projects": [{"id": row.id, "session_id": row.session_id, "name": row.data["name"],
                          "selected": row.selected} for row in projects],
            "tasks": tasks, "interview": interview, "applications": counts,
            "next_action": next_action(action, tasks, interview, match, target)}
