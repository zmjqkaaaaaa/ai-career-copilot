from sqlalchemy import select
from app.ai.evidence import redact_text
from app.models.career import CareerAnalysis
from app.models.discovery import DiscoveryMessage, InterestRecord
from app.models.job import JobMatch, JobPosition
from app.models.user_profile import UserProfile
from app.services.career import analysis_query, read_analysis

def background(db, user_id: int, source=None) -> dict:
    profile = db.scalar(select(UserProfile).where(UserProfile.user_id == user_id))
    result = {}
    if profile is not None:
        result = {key: getattr(profile, key) for key in (
            "undergraduate_major", "graduate_major", "undergraduate_degree", "target_position", "interested_industries",
            "skills", "internship_experience", "project_experience",
        )}
        for key in ("internship_experience", "project_experience"):
            result[key] = [item.get("title") for item in (result[key] or []) if item.get("title")]
    analysis = analysis_query(user_id)
    if source:
        analysis = analysis.where(CareerAnalysis.id == source["analysis_id"])
    latest = db.execute(analysis.order_by(CareerAnalysis.id.desc()).limit(1)).first()
    if latest:
        profile_result = read_analysis(db, user_id, latest[0].id, None)["report"]
        result["career_analysis_id"] = latest[0].id
        result["abilities"] = [{**{key: item[key] for key in ("name", "level", "status")},
                                "sources": item["sources"][:2]} for item in profile_result["skills"]
                               if item["status"] != "unknown"][:16]
    if source:
        result["target_position"] = source["role"]
        result["job_match"] = {key: source[key] for key in ("match_id", "revision", "role", "score", "gaps")}
        result["job_match"]["id"] = result["job_match"].pop("match_id")
        return result
    job_row = db.execute(select(JobMatch, JobPosition.position_name).join(JobPosition)
                         .where(JobMatch.user_id == user_id, JobPosition.user_id == user_id, JobMatch.revision == JobPosition.revision)
                         .order_by(JobMatch.id.desc()).limit(1)).first()
    if job_row:
        match, title = job_row
        result["job_match"] = {"id": match.id, "revision": match.revision, "role": title, "score": match.overall_score,
                               "gaps": [row["name"] for row in match.score_details.get("hard_flags", [])][:8]}
    return result

def recent_messages(db, session_id: int) -> list[dict]:
    messages = db.scalars(select(DiscoveryMessage).where(DiscoveryMessage.session_id == session_id)
                          .order_by(DiscoveryMessage.id.desc()).limit(12)).all()
    return [{"id": item.id, "role": item.role, "text": redact_text(item.content[:1200])} for item in reversed(messages)]

def interests(db, session_id: int) -> list[dict]:
    return list(db.scalars(select(InterestRecord.data).where(InterestRecord.session_id == session_id)
                           .order_by(InterestRecord.id.desc()).limit(16)))

def validate_turn(turn, messages):
    user_text = {item["id"]: item["text"] for item in messages if item["role"] == "user"}
    for item in turn.interests:
        if item.origin == "stated" and item.name.casefold() not in user_text.get(item.evidence_message_id, "").casefold():
            item.origin, item.confidence, item.evidence_message_id = "inferred", "low", None
    return turn
