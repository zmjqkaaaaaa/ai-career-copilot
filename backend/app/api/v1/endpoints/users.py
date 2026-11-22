from fastapi import APIRouter, Request, Response

from app.api.dependencies import AppSettings, CurrentUser, Database
from app.core.security import cookie_name
from app.schemas.user import AccountDeletionRequest, UserRead
from app.services.account_deletion import delete_account

router = APIRouter(prefix="/users", tags=["users"])

@router.get("/me", response_model=UserRead)
def read_current_user(user: CurrentUser):
    return user


@router.delete("/me", status_code=202)
def remove_current_user(body: AccountDeletionRequest, request: Request, response: Response,
                        user: CurrentUser, db: Database, settings: AppSettings):
    request.app.state.auth_limiter.check(request, "account_deletion", 5)
    delete_account(db, user.id, body.password.get_secret_value())
    response.delete_cookie(cookie_name, httponly=True, secure=settings.app_env == "production",
                           samesite="lax", path="/api/v1")
    return {"status": "deleted", "file_cleanup": "scheduled"}
