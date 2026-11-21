from typing import Annotated
from urllib.parse import urlsplit

from fastapi import APIRouter, Query

from app.api.dependencies import AppSettings, CurrentUser, Database
from app.models.career import CareerAnalysis
from app.models.resume import ResumeContent
from app.schemas.career import AnalyzeRequest, JobRead
from app.services.career import analysis_query, analysis_summary, read_analysis
from app.services.resume_jobs import start_job

router = APIRouter(prefix="/career", tags=["career"])

@router.get("/provider")
def provider(_user: CurrentUser, settings: AppSettings):
    return {"host": urlsplit(settings.llm_base_url or "").hostname, "model": settings.llm_model}

@router.post("/analyze", status_code=202, response_model=JobRead)
def analyze(body: AnalyzeRequest, user: CurrentUser, db: Database, settings: AppSettings):
    return start_job(db, user.id, body.resume_id, "analyze", body, settings)

@router.get("/profile")
def profile(user: CurrentUser, db: Database, analysis_id: Annotated[int | None, Query(gt=0)] = None,
            resume_id: Annotated[int | None, Query(gt=0)] = None):
    return read_analysis(db, user.id, analysis_id, resume_id)

@router.get("/analyses")
def history(user: CurrentUser, db: Database, resume_id: Annotated[int | None, Query(gt=0)] = None,
            offset: Annotated[int, Query(ge=0)] = 0):
    statement = analysis_query(user.id)
    if resume_id:
        statement = statement.where(ResumeContent.resume_id == resume_id)
    return [analysis_summary(analysis, owner_resume) for analysis, owner_resume in
            db.execute(statement.order_by(CareerAnalysis.id.desc()).offset(offset).limit(50))]
