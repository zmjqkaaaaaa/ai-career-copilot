from typing import Annotated

from fastapi import Depends, Request
from fastapi.security import OAuth2PasswordBearer
from jwt import InvalidTokenError
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.errors import ApiError, not_authenticated
from app.core.security import cookie_name, token_user_id
from app.db.session import get_db
from app.models.user import User

Database = Annotated[Session, Depends(get_db)]
AppSettings = Annotated[Settings, Depends(get_settings)]
bearer = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login", auto_error=False)

def require_browser_origin(request: Request, settings: Settings) -> None:
    if request.headers.get("origin") not in settings.cors_origins or request.headers.get("x-csrf-protection") != "1":
        raise ApiError(403, "INVALID_ORIGIN", "请求来源未通过校验")

def current_user(request: Request, db: Database, settings: AppSettings,
                 token: Annotated[str | None, Depends(bearer)]) -> User:
    if request.headers.get("authorization"):
        if not token:
            raise not_authenticated()
        audience = "api"
    else:
        token = request.cookies.get(cookie_name)
        audience = "browser"
        if token and request.method not in {"GET", "HEAD", "OPTIONS"}:
            require_browser_origin(request, settings)
    if not token:
        raise not_authenticated()
    try:
        user_id = token_user_id(token, audience, settings)
    except InvalidTokenError:
        raise not_authenticated() from None
    user = db.get(User, user_id)
    if not user or not user.is_active:
        raise not_authenticated()
    return user

CurrentUser = Annotated[User, Depends(current_user)]
