from sqlalchemy import select
from sqlalchemy.dialects.mysql import insert
from sqlalchemy.orm import Session

from app.core.errors import ApiError
from app.models.user_profile import UserProfile
from app.schemas.profile import ProfileWrite

def get_profile(db: Session, user_id: int) -> UserProfile:
    profile = db.scalar(select(UserProfile).where(UserProfile.user_id == user_id))
    if profile is None:
        raise ApiError(404, "PROFILE_NOT_FOUND", "尚未创建个人档案")
    return profile

def save_profile(db: Session, user_id: int, data: ProfileWrite) -> UserProfile:
    values = data.model_dump(mode="json")
    statement = insert(UserProfile).values(user_id=user_id, **values)
    # The unique user_id constraint makes first save and later edits one database operation.
    db.execute(statement.on_duplicate_key_update(**{field: statement.inserted[field] for field in values}))
    profile = get_profile(db, user_id)
    db.commit()
    return profile
