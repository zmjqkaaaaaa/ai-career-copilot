from datetime import timedelta
from hashlib import sha256
import hmac
import json
import logging
from urllib.parse import urlsplit

from sqlalchemy import select
from app.ai import discovery_prompts as prompts
from app.ai.evidence import redact_text
from app.ai.provider import Provider, model_configured, provider_fingerprint
from app.core.config import get_settings
from app.core.errors import ApiError
from app.models import career, job, resume, user, user_profile
from app.models.discovery import (
    CompetitorRecord, DiscoveryMessage, DiscoverySession, DiscoveryTask, InterestRecord,
    MarketResearchRun, OpportunityAnalysis, PainPoint, ProductPrd, ProjectRecommendation,
)
from app.schemas.discovery import Opportunity, PainResult, PRD_FIELDS, PrdModel, Projects, Turn
from app.services.competitor_analysis_service import analyze_competitors
from app.services.interest_discovery_service import background, interests, recent_messages, validate_turn
from app.services.market_research_service import SEARCH_HOST, collect_sources
from app.services.opportunity_evaluation_service import LABELS, evaluate
from app.services.pain_point_service import evidence_entries, validate_pains
from app.services.project_recommendation_service import rank_projects
from app.services.resumes import utc_now

logger = logging.getLogger(__name__)
ACTIVE = ("queued", "running")
PROMPTS = {"turn": prompts.TURN, "pain": prompts.PAIN, "research": prompts.RESEARCH,
           "opportunity": prompts.OPPORTUNITY, "recommend": prompts.RECOMMEND, "prd": prompts.PRD}

def own(db, model, owner: int, identifier: int | None, lock=False):
    query = select(model).where(model.id == identifier, model.user_id == owner)
    record = db.scalar(query.with_for_update() if lock else query)
    if record is None:
        raise ApiError(404, "DISCOVERY_NOT_FOUND", "未找到该探索记录")
    return record

def in_session(db, model, session, identifier):
    record = own(db, model, session.user_id, identifier)
    if record.session_id != session.id:
        raise ApiError(404, "DISCOVERY_NOT_FOUND", "未找到该会话中的记录")
    return record

def scoped(db, model, session, limit=40):
    return db.scalars(select(model).where(model.session_id == session.id, model.user_id == session.user_id)
                     .order_by(model.id.desc()).limit(limit)).all()

def busy(db, session_id):
    return db.scalar(select(DiscoveryTask.id).where(DiscoveryTask.session_id == session_id,
                     DiscoveryTask.state.in_(ACTIVE)).limit(1).with_for_update())

def scrub(value):
    if isinstance(value, str):
        return redact_text(value)
    if isinstance(value, dict):
        return {key: item if key == "url" and isinstance(item, str) else scrub(item) for key, item in value.items()}
    if isinstance(value, list):
        return [scrub(item) for item in value]
    return value

def source_map(pain, research, profile):
    result = evidence_entries(pain)
    if research:
        for item in research.data["sources"]:
            result[f"source:{item['id']}"] = {"kind": "market_source", "detail": item["excerpt"], "url": item["url"]}
    for index, ability in enumerate(profile.get("abilities", []), 1):
        result[f"ability:{index}"] = {"kind": "ai_inference" if ability["status"] == "inferred" else "ability", "detail": ability}
    if profile.get("job_match"):
        result["job:1"] = {"kind": "job_match", "detail": profile["job_match"]}
    return result

def latest_prd(db, project_id):
    return db.scalar(select(ProductPrd).where(ProductPrd.recommendation_id == project_id)
                     .order_by(ProductPrd.version.desc()).limit(1).with_for_update())

def inputs(db, session, body):
    if body.kind in {"turn", "pain"}:
        messages = recent_messages(db, session.id)
        if body.kind == "turn":
            if not body.message:
                raise ApiError(422, "DISCOVERY_MESSAGE_REQUIRED", "请先填写本轮内容")
            messages.append({"id": None, "role": "user", "text": redact_text(body.message)})
        return scrub({"messages": messages, "known_interests": interests(db, session.id), "mode": session.mode,
                      "direction": session.direction, "weekly_hours": session.weekly_hours,
                      "background": background(db, session.user_id)})
    if body.kind in {"research", "opportunity"}:
        pain = in_session(db, PainPoint, session, body.reference_id)
        if body.kind == "research":
            if not body.queries and not body.sources:
                raise ApiError(422, "DISCOVERY_SOURCE_REQUIRED", "请填写搜索词或补录公开来源")
            if body.queries and not get_settings().tavily_api_key:
                raise ApiError(503, "DISCOVERY_SEARCH_NOT_CONFIGURED", "尚未配置 Tavily，可补录公开来源")
            return scrub({"pain_point_id": pain.id, "pain_revision": pain.revision, "topic": pain.data["pain_point_name"],
                          "queries": body.queries, "sources": [source.model_dump(mode="json") for source in body.sources]})
        research = in_session(db, MarketResearchRun, session, body.research_id) if body.research_id else None
        if research and research.pain_point_id != pain.id:
            raise ApiError(422, "DISCOVERY_RESEARCH_MISMATCH", "请选择该痛点的市场研究")
        return scrub({"pain_point_id": pain.id, "pain_revision": pain.revision, "pain": pain.data,
                      "research_id": research.id if research else None,
                      "evidence": source_map(pain.data, research, background(db, session.user_id)), "dimensions": LABELS})
    if body.kind == "recommend":
        opportunity = in_session(db, OpportunityAnalysis, session, body.reference_id)
        pain = in_session(db, PainPoint, session, opportunity.pain_point_id)
        research = (in_session(db, MarketResearchRun, session, opportunity.research_id)
                    if opportunity.research_id else None)
        previous = scoped(db, ProjectRecommendation, session, 8) if body.regenerate else []
        return scrub({"opportunity_id": opportunity.id, "opportunity": opportunity.data, "pain": pain.data,
                      "market_research": research.data if research else None,
                      "background": background(db, session.user_id), "interests": interests(db, session.id),
                      "direction": session.direction, "weekly_hours": session.weekly_hours,
                      "previous_directions": [item.data["name"] for item in previous]})
    project = in_session(db, ProjectRecommendation, session, body.reference_id)
    if not project.selected:
        raise ApiError(409, "DISCOVERY_PROJECT_NOT_SELECTED", "请先选定方案")
    opportunity = in_session(db, OpportunityAnalysis, session, project.opportunity_id)
    prior = latest_prd(db, project.id) if body.regenerate else None
    return scrub({"project_id": project.id, "project": project.data, "opportunity": opportunity.data,
                  "previous_version": prior.version if prior else None})

def sign(session, body, payload, settings):
    encoded = json.dumps([session.user_id, session.id, body.kind, PROMPTS[body.kind].version,
                          provider_fingerprint(settings), body.regenerate, payload], ensure_ascii=False, sort_keys=True)
    return hmac.new(settings.jwt_secret.get_secret_value().encode(), encoded.encode(), sha256).hexdigest()

def prepare(db, session, body, settings):
    payload = inputs(db, session, body)
    return {"payload": payload, "approval": sign(session, body, payload, settings),
            "model_host": urlsplit(settings.llm_base_url or "").hostname,
            "search_host": SEARCH_HOST if body.kind == "research" and body.queries else None}

def enqueue(db, session, body, settings):
    existing = db.scalar(select(DiscoveryTask).where(DiscoveryTask.session_id == session.id,
                        DiscoveryTask.request_key == body.approval).with_for_update())
    if existing:
        if existing.kind != body.kind:
            raise ApiError(409, "DISCOVERY_PREVIEW_CHANGED", "请重新核对本次内容")
        return existing
    if not model_configured(settings):
        raise ApiError(503, "LLM_NOT_CONFIGURED", "请先配置模型服务")
    if busy(db, session.id):
        raise ApiError(409, "DISCOVERY_BUSY", "已有探索任务在处理")
    checked = prepare(db, session, body, settings)
    if not hmac.compare_digest(checked["approval"], body.approval):
        raise ApiError(409, "DISCOVERY_PREVIEW_CHANGED", "内容已更新，请重新核对发送预览")
    if body.kind == "turn":
        message = DiscoveryMessage(session_id=session.id, user_id=session.user_id, content=body.message, role="user")
        db.add(message)
        db.flush()
        checked["payload"]["messages"][-1]["id"] = message.id
    task = DiscoveryTask(session_id=session.id, user_id=session.user_id, kind=body.kind,
                         request_key=body.approval, payload=checked["payload"], provider=provider_fingerprint(settings))
    db.add(task)
    db.flush()
    db.commit()
    return task

def compute(task, settings, provider_factory, search):
    if task.provider != provider_fingerprint(settings):
        raise ApiError(409, "MODEL_CONFIG_CHANGED", "模型配置已变，请重新预览")
    payload = task.payload
    if task.kind == "research":
        sources = search(settings, payload["queries"], payload["sources"])
        if not sources:
            return {"sources": [], "competitors": [], "findings": [], "status": "insufficient_results"}
    provider = provider_factory(settings)
    try:
        if task.kind == "turn":
            return validate_turn(provider.generate(prompts.TURN, payload, Turn), payload["messages"]).model_dump()
        if task.kind == "pain":
            return validate_pains(provider.generate(prompts.PAIN, payload, PainResult), payload["messages"]).model_dump()
        if task.kind == "research":
            competitors, findings = analyze_competitors(provider, payload["topic"], sources)
            return {"sources": sources, "competitors": competitors, "findings": findings,
                    "status": "completed" if competitors or findings else "insufficient_results"}
        if task.kind == "opportunity":
            result = provider.generate(prompts.OPPORTUNITY, payload, Opportunity)
            return evaluate(result, payload["evidence"])
        if task.kind == "recommend":
            return rank_projects(provider.generate(prompts.RECOMMEND, payload, Projects), payload["weekly_hours"])
        result = provider.generate(prompts.PRD, payload, PrdModel)
        if set(result.sections) != set(PRD_FIELDS):
            raise ApiError(502, "DISCOVERY_PRD_INCOMPLETE", "草稿未包含完整章节，可重试")
        content = "\n\n".join([f"# {result.title}"] + [f"## {label}\n\n{result.sections[key]}" for key, label in PRD_FIELDS.items()])
        return {"title": result.title, "content": content}
    finally:
        provider.close()

def complete(db, task, result):
    base = {"session_id": task.session_id, "user_id": task.user_id}
    data = task.payload
    if task.kind == "turn":
        reply = DiscoveryMessage(**base, role="assistant", content=result["reply"], details={
            "questions": result["questions"], "learning_note": result["learning_note"],
        })
        db.add(reply)
        db.add_all(InterestRecord(**base, data=item) for item in result["interests"])
        record = reply
    elif task.kind == "pain":
        records = [PainPoint(**base, data=item) for item in result["pain_points"]]
        db.add_all(records)
        record = records[0] if records else None
    elif task.kind == "research":
        record = MarketResearchRun(**base, pain_point_id=data["pain_point_id"], data={
            **{key: value for key, value in result.items() if key != "competitors"},
            "queries": data["queries"], "topic": data["topic"], "pain_revision": data["pain_revision"],
        })
        db.add(record)
        db.flush()
        db.add_all(CompetitorRecord(user_id=task.user_id, research_id=record.id, data=item)
                   for item in result["competitors"])
    elif task.kind == "opportunity":
        record = OpportunityAnalysis(**base, pain_point_id=data["pain_point_id"], research_id=data["research_id"],
                                     data={**result, "pain_revision": data["pain_revision"]})
        db.add(record)
    elif task.kind == "recommend":
        records = [ProjectRecommendation(**base, opportunity_id=data["opportunity_id"], batch_id=task.id, data=item)
                   for item in result]
        db.add_all(records)
        record = records[0]
    else:
        existing = latest_prd(db, data["project_id"])
        record = ProductPrd(user_id=task.user_id, recommendation_id=data["project_id"],
                            version=existing.version + 1 if existing else 1, based_on=existing.id if existing else None,
                            origin="ai_draft", **result)
        db.add(record)
    db.flush()
    return record.id if record else None

def run_discovery_once(factory, provider_factory=Provider, search=collect_sources):
    with factory() as db:
        stale = db.scalars(select(DiscoveryTask).where(DiscoveryTask.state == "running",
                          DiscoveryTask.started_at < utc_now() - timedelta(minutes=10)).limit(30).with_for_update(skip_locked=True)).all()
        for item in stale:
            item.state, item.error_code = "failed", "DISCOVERY_INTERRUPTED"
        task = db.scalar(select(DiscoveryTask).where(DiscoveryTask.state == "queued")
                         .order_by(DiscoveryTask.id).limit(1).with_for_update(skip_locked=True))
        if task is None:
            db.commit()
            return False
        task.state, task.started_at = "running", utc_now()
        db.commit()
    error = None
    try:
        result = compute(task, get_settings(), provider_factory, search)
        with factory() as db:
            db.get(DiscoverySession, task.session_id, with_for_update=True)
            current = db.get(DiscoveryTask, task.id, with_for_update=True)
            if current and current.state == "running" and current.attempt == task.attempt:
                current.result_id = complete(db, current, result)
                current.state = "succeeded"
                db.commit()
        return True
    except ApiError as exc:
        error = exc.code
    except Exception as exc:
        logger.error("discovery task %s failed (%s)", task.id, type(exc).__name__)
        error = "DISCOVERY_TASK_FAILED"
    with factory() as db:
        current = db.get(DiscoveryTask, task.id, with_for_update=True)
        if current and current.state == "running" and current.attempt == task.attempt:
            current.state, current.error_code = "failed", error
            db.commit()
    return True
