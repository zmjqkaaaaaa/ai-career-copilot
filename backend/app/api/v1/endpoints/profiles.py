from fastapi import APIRouter

from app.api.dependencies import CurrentUser, Database
from app.schemas.profile import ProfileRead, ProfileResumeDraft, ProfileWrite
from app.services.profile_resume import resume_profile_draft
from app.services.profile_service import get_profile, save_profile

router = APIRouter(prefix="/profiles", tags=["profiles"])

@router.get("/me", response_model=ProfileRead)
def read_profile(user: CurrentUser, db: Database):
    return get_profile(db, user.id)

@router.get("/me/resume-draft", response_model=ProfileResumeDraft | None)
def read_resume_draft(user: CurrentUser, db: Database):
    return resume_profile_draft(db, user.id)

@router.put("/me", response_model=ProfileRead)
def upsert_profile(body: ProfileWrite, user: CurrentUser, db: Database):
    return save_profile(db, user.id, body)
