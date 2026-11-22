from fastapi import APIRouter, Query
from fastapi.responses import Response
from sqlalchemy import select, update

from app.api.dependencies import AppSettings, CurrentUser, Database
from app.ai.provider import provider_fingerprint
from app.core.errors import ApiError
from app.models.discovery import (
    CompetitorRecord, DiscoveryMessage, DiscoverySession, DiscoveryTask, InterestRecord,
    MarketResearchRun, OpportunityAnalysis, PainPoint, ProductPrd, ProjectRecommendation,
)
from app.schemas.discovery import (
    Competitor, Interest, JobInput, JobSubmit, Opportunity, Pain, PrdEdit, ProjectEdit, SessionCreate, SessionInput,
)
from app.services.career_context import discovery_binding
from app.services.competitor_analysis_service import grounded_claim
from app.services.discovery_workflow import background, busy, enqueue, in_session, latest_prd, own, prepare, scoped
from app.services.opportunity_evaluation_service import evaluate

router = APIRouter(tags=["product discovery"])

def show(record, names=""):
    fields = ("id created_at " + names).split()
    return {name: getattr(record, name) for name in fields}

def task_view(item):
    return show(item, "kind state attempt result_id error_code")

def session_view(item):
    return show(item, "title mode direction weekly_hours updated_at source_snapshot")

def check_idle(db, session_id):
    if busy(db, session_id):
        raise ApiError(409, "DISCOVERY_BUSY", "请等待当前任务结束")

def submit(path_kind, session, body, settings, db):
    if body.kind != path_kind:
        raise ApiError(422, "DISCOVERY_TASK_KIND", "任务类型与接口不匹配")
    return task_view(enqueue(db, session, body, settings))

@router.post("/discovery/sessions", status_code=201)
def create_session(body: SessionCreate, user: CurrentUser, db: Database):
    source = discovery_binding(db, user.id, body.job_match_id, body.application_id)
    fields = body.model_dump(exclude={"job_match_id", "application_id"})
    if source:
        fields["direction"] = source["role"]
    item = DiscoverySession(user_id=user.id, **fields, source_snapshot=source,
                            job_match_id=source["match_id"] if source else None, application_id=body.application_id)
    db.add(item)
    db.flush()
    db.refresh(item)
    db.commit()
    return session_view(item)

@router.get("/discovery/sessions")
def sessions(user: CurrentUser, db: Database):
    return [session_view(item) for item in db.scalars(select(DiscoverySession).where(
        DiscoverySession.user_id == user.id).order_by(DiscoverySession.id.desc())).all()]

@router.get("/discovery/sessions/{session_id}")
def session_detail(session_id: int, user: CurrentUser, db: Database, settings: AppSettings):
    item = own(db, DiscoverySession, user.id, session_id)
    return {**session_view(item), "background": background(db, user.id, item.source_snapshot),
            "search_configured": bool(settings.tavily_api_key and settings.tavily_api_key.get_secret_value().strip()),
            "messages": [show(record, "role content details") for record in reversed(scoped(db, DiscoveryMessage, item, 100))],
            "interests": [show(record, "data") for record in scoped(db, InterestRecord, item)],
            "pain_points": [show(record, "data revision") for record in scoped(db, PainPoint, item)],
            "research": [show(record, "pain_point_id data") for record in scoped(db, MarketResearchRun, item)],
            "opportunities": [show(record, "pain_point_id research_id data") for record in scoped(db, OpportunityAnalysis, item)],
            "projects": [show(record, "opportunity_id batch_id data favorite selected") for record in scoped(db, ProjectRecommendation, item, 100)],
            "tasks": [task_view(record) for record in scoped(db, DiscoveryTask, item)]}

@router.put("/discovery/sessions/{session_id}")
def edit_session(session_id: int, body: SessionInput, user: CurrentUser, db: Database):
    item = own(db, DiscoverySession, user.id, session_id, lock=True)
    check_idle(db, item.id)
    fields = body.model_dump(exclude={"direction"} if item.source_snapshot else None)
    for field, value in fields.items():
        setattr(item, field, value)
    db.commit()
    return session_view(item)

@router.put("/discovery/sessions/{session_id}/interests/{interest_id}")
def edit_interest(session_id: int, interest_id: int, body: Interest, user: CurrentUser, db: Database):
    session = own(db, DiscoverySession, user.id, session_id, lock=True)
    check_idle(db, session.id)
    record = in_session(db, InterestRecord, session, interest_id)
    record.data = {**body.model_dump(), "origin": "stated", "evidence_message_id": None}
    db.commit()
    return show(record, "data")

@router.post("/discovery/sessions/{session_id}/preview")
def preview_task(session_id: int, body: JobInput, user: CurrentUser, db: Database, settings: AppSettings):
    return prepare(db, own(db, DiscoverySession, user.id, session_id), body, settings)

@router.post("/discovery/sessions/{session_id}/messages", status_code=202)
def send_message(session_id: int, body: JobSubmit, user: CurrentUser, db: Database, settings: AppSettings):
    return submit("turn", own(db, DiscoverySession, user.id, session_id, lock=True), body, settings, db)

@router.get("/discovery/sessions/{session_id}/messages")
def message_history(session_id: int, user: CurrentUser, db: Database, before: int | None = None):
    own(db, DiscoverySession, user.id, session_id)
    stmt = select(DiscoveryMessage).where(DiscoveryMessage.session_id == session_id, DiscoveryMessage.user_id == user.id)
    if before:
        stmt = stmt.where(DiscoveryMessage.id < before)
    return [show(item, "role content details") for item in reversed(db.scalars(stmt.order_by(DiscoveryMessage.id.desc()).limit(100)).all())]

@router.post("/discovery/sessions/{session_id}/pain-points", status_code=202)
def extract_pains(session_id: int, body: JobSubmit, user: CurrentUser, db: Database, settings: AppSettings):
    return submit("pain", own(db, DiscoverySession, user.id, session_id, lock=True), body, settings, db)

@router.get("/pain-points")
def pains(user: CurrentUser, db: Database):
    return [show(record, "session_id revision data") for record in db.scalars(select(PainPoint)
            .where(PainPoint.user_id == user.id).order_by(PainPoint.id.desc()).limit(100)).all()]

@router.put("/pain-points/{pain_id}")
def edit_pain(pain_id: int, body: Pain, user: CurrentUser, db: Database, revision: int = Query(ge=1)):
    record = own(db, PainPoint, user.id, pain_id)
    own(db, DiscoverySession, user.id, record.session_id, lock=True)
    check_idle(db, record.session_id)
    db.refresh(record, with_for_update=True)
    if record.revision != revision:
        raise ApiError(409, "DISCOVERY_REVISION_CHANGED", "痛点已有更新，请刷新")
    if body.validation_status == "interview_reported" and not any(e.kind == "hearsay" for e in body.evidence):
        raise ApiError(422, "DISCOVERY_INTERVIEW_EVIDENCE", "请先补充访谈转述及其依据")
    record.data = body.model_dump()
    record.revision += 1
    db.commit()
    return show(record, "revision data")

@router.post("/research/competitors", status_code=202)
def research(session_id: int, body: JobSubmit, user: CurrentUser, db: Database, settings: AppSettings):
    return submit("research", own(db, DiscoverySession, user.id, session_id, lock=True), body, settings, db)

@router.get("/research/competitors/{research_id}")
def research_detail(research_id: int, user: CurrentUser, db: Database):
    record = own(db, MarketResearchRun, user.id, research_id)
    competitors = db.scalars(select(CompetitorRecord).where(CompetitorRecord.research_id == record.id,
                              CompetitorRecord.user_id == user.id).order_by(CompetitorRecord.id)).all()
    return {**show(record, "session_id pain_point_id data"), "competitors": [show(row, "data") for row in competitors]}

@router.put("/research/competitors/{research_id}/records/{competitor_id}")
def edit_competitor(research_id: int, competitor_id: int, body: Competitor, user: CurrentUser, db: Database):
    research = own(db, MarketResearchRun, user.id, research_id)
    record = own(db, CompetitorRecord, user.id, competitor_id, lock=True)
    if record.research_id != research.id:
        raise ApiError(404, "DISCOVERY_NOT_FOUND", "未找到该竞品")
    valid = {source["id"]: source for source in research.data["sources"]}
    record.data = {"product_name": body.product_name,
                   "official_source": body.official_source if valid.get(body.official_source, {}).get("source_type") == "official" else None,
                   **{name: grounded_claim(getattr(body, name), valid) for name in Competitor.model_fields
                      if name not in {"product_name", "official_source"}}}
    db.commit()
    return show(record, "data")

@router.post("/opportunities/evaluate", status_code=202)
def evaluate_opportunity(session_id: int, body: JobSubmit, user: CurrentUser, db: Database, settings: AppSettings):
    return submit("opportunity", own(db, DiscoverySession, user.id, session_id, lock=True), body, settings, db)

@router.get("/opportunities")
def opportunities(user: CurrentUser, db: Database):
    return [show(item, "session_id pain_point_id research_id data") for item in db.scalars(select(OpportunityAnalysis)
            .where(OpportunityAnalysis.user_id == user.id).order_by(OpportunityAnalysis.id.desc()).limit(100)).all()]

@router.put("/opportunities/{opportunity_id}", status_code=201)
def edit_opportunity(opportunity_id: int, body: Opportunity, user: CurrentUser, db: Database):
    previous = own(db, OpportunityAnalysis, user.id, opportunity_id)
    session = own(db, DiscoverySession, user.id, previous.session_id, lock=True)
    check_idle(db, session.id)
    result = evaluate(body, previous.data["evidence"])
    entry = OpportunityAnalysis(user_id=user.id, session_id=session.id, pain_point_id=previous.pain_point_id,
                                research_id=previous.research_id, data={**result, "based_on": previous.id,
                                "pain_revision": previous.data["pain_revision"]})
    db.add(entry)
    db.flush()
    db.refresh(entry)
    db.commit()
    return show(entry, "pain_point_id research_id data")

@router.post("/projects/recommendations", status_code=202)
def recommend(session_id: int, body: JobSubmit, user: CurrentUser, db: Database, settings: AppSettings):
    return submit("recommend", own(db, DiscoverySession, user.id, session_id, lock=True), body, settings, db)

@router.get("/projects/recommendations")
def projects(user: CurrentUser, db: Database):
    return [show(item, "session_id opportunity_id batch_id data favorite selected") for item in db.scalars(select(ProjectRecommendation)
            .where(ProjectRecommendation.user_id == user.id).order_by(ProjectRecommendation.id.desc()).limit(100)).all()]

@router.get("/projects/recommendations/{project_id}")
def project_detail(project_id: int, user: CurrentUser, db: Database):
    return show(own(db, ProjectRecommendation, user.id, project_id), "session_id opportunity_id batch_id data favorite selected")

@router.put("/projects/recommendations/{project_id}")
def edit_project(project_id: int, body: ProjectEdit, user: CurrentUser, db: Database):
    record = own(db, ProjectRecommendation, user.id, project_id)
    session = own(db, DiscoverySession, user.id, record.session_id, lock=True)
    check_idle(db, session.id)
    db.refresh(record, with_for_update=True)
    if body.favorite is not None:
        record.favorite = body.favorite
    if body.selected:
        db.execute(update(ProjectRecommendation).where(ProjectRecommendation.session_id == session.id).values(selected=False))
        record.selected = True
    elif body.selected is False:
        record.selected = False
    if body.project:
        new = body.project.model_dump()
        new["estimated_weeks"] = round(new["estimated_hours"] / session.weekly_hours, 1) if session.weekly_hours else None
        new["budget_fit"] = new["estimated_weeks"] <= 4 if new["estimated_weeks"] is not None else None
        record.data = new
    db.commit()
    return show(record, "data favorite selected")

@router.post("/projects/recommendations/{project_id}/prd", status_code=202)
def generate_prd(project_id: int, body: JobSubmit, user: CurrentUser, db: Database, settings: AppSettings):
    project = own(db, ProjectRecommendation, user.id, project_id)
    if project.id != body.reference_id:
        raise ApiError(422, "DISCOVERY_PROJECT_MISMATCH", "请核对选定项目")
    return submit("prd", own(db, DiscoverySession, user.id, project.session_id, lock=True), body, settings, db)

@router.get("/projects/recommendations/{project_id}/prds")
def prd_versions(project_id: int, user: CurrentUser, db: Database):
    own(db, ProjectRecommendation, user.id, project_id)
    return [show(record, "recommendation_id version title origin based_on") for record in db.scalars(select(ProductPrd).where(
        ProductPrd.recommendation_id == project_id, ProductPrd.user_id == user.id).order_by(ProductPrd.version.desc())).all()]

@router.get("/prds/{prd_id}")
def read_prd(prd_id: int, user: CurrentUser, db: Database):
    return show(own(db, ProductPrd, user.id, prd_id), "recommendation_id version title content origin based_on")

@router.put("/prds/{prd_id}", status_code=201)
def save_prd(prd_id: int, body: PrdEdit, user: CurrentUser, db: Database):
    previous = own(db, ProductPrd, user.id, prd_id)
    project = own(db, ProjectRecommendation, user.id, previous.recommendation_id)
    session = own(db, DiscoverySession, user.id, project.session_id, lock=True)
    check_idle(db, session.id)
    latest = latest_prd(db, project.id)
    if latest.id != previous.id or previous.version != body.version:
        raise ApiError(409, "DISCOVERY_PRD_VERSION_CHANGED", "请在最新版本上编辑")
    record = ProductPrd(user_id=user.id, recommendation_id=project.id, version=latest.version + 1, based_on=previous.id,
                        title=body.title, content=body.content, origin="user_edit")
    db.add(record)
    db.flush()
    db.refresh(record)
    db.commit()
    return show(record, "recommendation_id version title content origin based_on")

@router.get("/prds/{prd_id}/markdown")
def export_prd(prd_id: int, user: CurrentUser, db: Database):
    record = own(db, ProductPrd, user.id, prd_id)
    return Response(record.content, media_type="text/markdown",
                    headers={"Content-Disposition": f'attachment; filename="prd-{record.id}-v{record.version}.md"'})

@router.get("/discovery/tasks/{task_id}")
def task_status(task_id: int, user: CurrentUser, db: Database):
    return task_view(own(db, DiscoveryTask, user.id, task_id))

@router.post("/discovery/tasks/{task_id}/retry", status_code=202)
def retry(task_id: int, user: CurrentUser, db: Database, settings: AppSettings):
    task = own(db, DiscoveryTask, user.id, task_id)
    own(db, DiscoverySession, user.id, task.session_id, lock=True)
    db.refresh(task, with_for_update=True)
    if task.state != "failed" or task.attempt >= 3 or busy(db, task.session_id):
        raise ApiError(409, "DISCOVERY_RETRY_UNAVAILABLE", "该任务当前无法重试")
    if task.provider != provider_fingerprint(settings):
        raise ApiError(409, "MODEL_CONFIG_CHANGED", "模型配置已变，请重新预览")
    task.state, task.error_code, task.started_at = "queued", None, None
    task.attempt += 1
    db.commit()
    return task_view(task)
