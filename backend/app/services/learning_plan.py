from datetime import date, timedelta
from hashlib import sha256
import json

from sqlalchemy import select

from app.models.career import CareerAnalysis, SkillEvidence, SkillProfile
from app.models.code_project import CodeProject, ProjectSnapshot, QuizAttempt
from app.models.discovery import DiscoverySession, InterestRecord, PainPoint, ProductPrd, ProjectRecommendation
from app.models.interview import InterviewReport, InterviewSession, InterviewTrainingTask
from app.models.job import JobMatch, JobPosition
from app.models.learning import LearningEvaluation, LearningMastery, LearningPath, LearningSubmission, LearningTask
from app.models.user_profile import UserProfile
from app.services.career import analysis_query
from app.services.learning_catalog import CATEGORIES, TOPICS


def latest(db, model, user):
    return db.scalar(select(model).where(model.user_id == user).order_by(model.id.desc()).limit(1))


def diagnosis(db, user):
    profile = db.scalar(select(UserProfile).where(UserProfile.user_id == user))
    preferences = db.scalar(select(DiscoverySession).where(DiscoverySession.user_id == user,
                            DiscoverySession.weekly_hours.is_not(None)).order_by(DiscoverySession.id.desc()).limit(1))
    job = db.scalar(select(JobPosition).where(JobPosition.user_id == user).order_by(JobPosition.id.desc()).limit(1))
    target = (job.position_name if job else None) or (profile.target_position if profile else None) or "AI 产品经理"
    rows = {key: {"topic": key, "title": spec["title"], "category": spec["category"], "status": "unknown",
                  "confidence": "待验证", "level": None, "last_verified_at": None, "evidence": [], "priority": 0}
            for key, spec in TOPICS.items()}

    def add(text, source, ref, status="inferred", priority=0, topic=None):
        if not text:
            return
        value = str(text)
        for key, row in rows.items():
            if topic != key and (topic or not any(term in value.lower() for term in TOPICS[key]["terms"])):
                continue
            row["evidence"].append({"source": source, "ref": ref, "text": value[:230], "status": status})
            row["priority"] += priority
            if row["status"] == "unknown" or status == "self_reported":
                row["status"] = status
                row["confidence"] = "低"

    if profile:
        for skill in (profile.skills or []) + (profile.interested_industries or []):
            add(skill, "个人档案", profile.id, "self_reported")
        for item in (profile.project_experience or [])[:6]:
            add(item.get("title"), "档案项目经历", profile.id, "self_reported")
    career = db.execute(analysis_query(user).order_by(CareerAnalysis.id.desc()).limit(1)).first()
    if career:
        for item in db.scalars(select(SkillProfile).where(SkillProfile.analysis_id == career[0].id)):
            if item.evidence_status != "unknown":
                evidence = db.scalar(select(SkillEvidence).where(SkillEvidence.skill_profile_id == item.id).limit(1))
                add(item.skill_name + " · " + (evidence.source_content if evidence else item.analysis_reason), "简历职业画像", career[0].id,
                    "inferred" if item.evidence_status == "inferred" else "self_reported")
    if job:
        add(job.job_description[:3200], "岗位 JD（学习优先级）", job.id, priority=3)
        match = db.scalar(select(JobMatch).where(JobMatch.user_id == user, JobMatch.job_id == job.id,
                          JobMatch.revision == job.revision).order_by(JobMatch.id.desc()).limit(1))
        if match:
            if match.overall_score is not None:
                add(f"匹配参考 {match.overall_score}，覆盖 {match.evidence_coverage}%",
                    "岗位匹配报告", match.id, topic="interview")
            for item in match.score_details.get("hard_flags", [])[:10]:
                add(item.get("name"), f"岗位差距 · 匹配参考 {match.overall_score}", match.id, priority=4)
    for model, label in ((InterestRecord, "兴趣探索"), (PainPoint, "痛点分析"), (ProjectRecommendation, "已选项目")):
        stmt = select(model).where(model.user_id == user).order_by(model.id.desc()).limit(6)
        if model is ProjectRecommendation:
            stmt = stmt.where(model.selected.is_(True))
        for row in db.scalars(stmt):
            add(" ".join(str(row.data.get(key, "")) for key in ("name", "pain_point_name", "target_user", "reason", "positioning")),
                label, row.id, priority=1, topic={PainPoint: "research", ProjectRecommendation: "mvp"}.get(model))
            if model is ProjectRecommendation:
                prd = db.scalar(select(ProductPrd).where(ProductPrd.user_id == user,
                                ProductPrd.recommendation_id == row.id).order_by(ProductPrd.version.desc()).limit(1))
                if prd:
                    add(f"{prd.title} · v{prd.version}（需求文档记录）", "项目 PRD", prd.id, topic="mvp", priority=2)
    quiz = db.scalars(select(QuizAttempt).join(ProjectSnapshot).join(CodeProject).where(CodeProject.user_id == user,
                      ProjectSnapshot.commit_sha == CodeProject.active_commit).order_by(QuizAttempt.id.desc()).limit(8))
    for item in quiz:
        topic = {"functions": "python", "api": "api", "database": "sql", "ai": "llm"}.get(item.data.get("dimension"), "project")
        add(f"代码理解测验参考分 {item.data.get('score')}（具体语言以仓库为准）", "项目掌握", item.id,
            topic="project" if topic == "python" else topic, priority=2)
    reports = db.scalars(select(InterviewReport).join(InterviewSession).where(
        InterviewSession.user_id == user).order_by(InterviewReport.id.desc()).limit(5))
    for report in reports:
        for item in report.data.get("weaknesses", [])[:5]:
            add(item.get("knowledge_point"), "面试薄弱项", report.id, priority=2)
        if report.data.get("answered"):
            add(f"完成 {report.data['answered']} 题，参考分 {report.data.get('score')}", "面试报告", report.id, topic="interview")
    training = db.scalars(select(InterviewTrainingTask).join(InterviewReport).join(InterviewSession)
                         .where(InterviewSession.user_id == user).order_by(InterviewTrainingTask.id.desc()).limit(5))
    for task in training:
        add(task.data.get("title"), "面试训练任务", task.id, topic="interview",
            priority=2 if task.state == "todo" else 0)
    evaluations = db.execute(select(LearningEvaluation, LearningSubmission.topic).join(
        LearningSubmission, LearningSubmission.id == LearningEvaluation.submission_id
    ).where(LearningEvaluation.user_id == user, LearningSubmission.user_id == user)
        .order_by(LearningEvaluation.id.desc()).limit(25))
    counted = {}
    for item, key in evaluations:
        if counted.get(key, 0) >= 2:
            continue
        counted[key] = counted.get(key, 0) + 1
        feedback = item.data
        add("作业反馈 · " + feedback["revision"], "AI 作业评估", item.id, topic=key,
            priority=3 if feedback["status"] == "needs_revision" else 0)
    for key, row in rows.items():
        event = db.scalar(select(LearningMastery).where(LearningMastery.user_id == user,
                          LearningMastery.topic == key).order_by(LearningMastery.id.desc()).limit(1))
        if event:
            row.update(status=event.data["status"], confidence="高" if event.data["status"] == "verified" else "待验证",
                       level=event.data["score"], last_verified_at=event.data["last_verified_at"])
            row["evidence"].insert(0, {"source": "阶段测评", "ref": event.assessment_id,
                                      "text": event.data["reason"], "status": event.data["status"]})
            if row["status"] != "verified":
                row["priority"] += 5
        row["evidence"] = row["evidence"][:10]
    return {"target": target, "categories": CATEGORIES, "topics": list(rows.values()),
            "suggested_minutes": min(1200, preferences.weekly_hours * 60) if preferences else None,
            "summary": {state: sum(row["status"] == state for row in rows.values())
                        for state in ("verified", "self_reported", "inferred", "unknown")}}


def make_path(db, user, minutes, goal, cause, report=None):
    report = report or diagnosis(db, user)
    old = latest(db, LearningPath, user)
    state = {row["topic"]: row for row in report["topics"]}
    completed = {key for key, row in state.items() if row["status"] == "verified"}
    old_order = [item["id"] for item in old.data["modules"]] if old else []
    order = []

    def visit(key):
        if key in completed or key in order:
            return
        for dependency in TOPICS[key]["requires"]:
            visit(dependency)
        order.append(key)

    ranked = sorted(TOPICS, key=lambda key: (
        -min(12, state[key]["priority"]) - 3 * bool(goal and any(term in goal.lower() for term in TOPICS[key]["terms"])),
        old_order.index(key) if key in old_order else len(TOPICS)))
    for key in ranked:
        visit(key)
    modules = [{**TOPICS[key], "reason": "证据显示需要复练" if state[key]["level"] is not None else
                "与观察到的岗位或学习方向有关" if state[key]["priority"] else "课程基础或先修"} for key in order]
    settings = {"target": report["target"], "goal": goal, "weekly_minutes": minutes, "modules": modules,
                "verified": sorted(completed), "current": report["summary"]}
    digest = sha256(json.dumps(settings, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
    if old and old.fingerprint == digest:
        return old
    path = LearningPath(user_id=user, version=old.version + 1 if old else 1, fingerprint=digest,
                        data={**settings, "reason": cause, "estimated_weeks": round(sum(item["minutes"] for item in modules) / minutes, 1)})
    db.add(path)
    db.flush()
    return path


def daily(db, user, path, today: date):
    if not path:
        return []
    modules = path.data["modules"]
    if not modules:
        return []
    week_start = today - timedelta(days=today.weekday())
    prior = list(db.scalars(select(LearningTask).where(LearningTask.user_id == user,
                       LearningTask.due >= week_start.isoformat(),
                       LearningTask.due <= (week_start + timedelta(days=6)).isoformat())))
    existing = [item for item in prior if item.due == today.isoformat() and
                (item.task_key.startswith("daily:") or item.task_key.startswith("manual:"))]
    if existing:
        return existing
    remaining = path.data["weekly_minutes"] - sum(item.data["minutes"] for item in prior)
    budget = min(remaining, (path.data["weekly_minutes"] + 6) // 7)
    if budget <= 0:
        return []
    done = set(path.data["verified"])
    done.update(db.scalars(select(LearningTask.topic).where(LearningTask.user_id == user, LearningTask.status == "completed")))
    topic = next((item for item in modules if item["id"] not in done and set(item["requires"]) <= done), None)
    if not topic:
        return []
    item = LearningTask(user_id=user, task_key=f"daily:{today.isoformat()}", topic=topic["id"], due=today.isoformat(),
                        data={**topic, "minutes": min(budget, topic["minutes"]),
                              "checkpoint": "在本次时间内完成一个最小可复核步骤"})
    db.add(item)
    db.flush()
    return [item]

