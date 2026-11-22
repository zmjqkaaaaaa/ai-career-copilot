from datetime import date

from fastapi import APIRouter

from app.api.dependencies import CurrentUser, Database
from app.schemas.dashboard import Dashboard
from app.services.dashboard_service import snapshot
from app.services.resumes import utc_now

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("", response_model=Dashboard)
def dashboard(user: CurrentUser, db: Database, day: date | None = None):
    return snapshot(db, user.id, day or utc_now().date())
