from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response
from fastapi.security import OAuth2PasswordRequestForm

from app.api.dependencies import AppSettings, Database, require_browser_origin
from app.core.security import cookie_name, issue_token
from app.schemas.auth import RegisterRequest, TokenResponse
from app.schemas.user import UserRead
from app.services.auth_service import authenticate, register

router = APIRouter(prefix="/auth", tags=["auth"])
LoginForm = Annotated[OAuth2PasswordRequestForm, Depends()]

@router.post("/register", status_code=201, response_model=UserRead)
def register_user(request: Request, body: RegisterRequest, db: Database):
    request.app.state.auth_limiter.check(request, "registration", 5)
    return register(db, body)

@router.post("/login", response_model=TokenResponse)
def login(request: Request, response: Response, form: LoginForm, db: Database, settings: AppSettings):
    request.app.state.auth_limiter.check(request, "login", 15)
    user = authenticate(db, form.username, form.password)
    response.headers["Cache-Control"] = "no-store"
    return TokenResponse(access_token=issue_token(user.id, "api", settings))

@router.post("/session", response_model=UserRead)
def create_session(request: Request, response: Response, form: LoginForm, db: Database, settings: AppSettings):
    require_browser_origin(request, settings)
    request.app.state.auth_limiter.check(request, "login", 15)
    user = authenticate(db, form.username, form.password)
    response.set_cookie(
        cookie_name, issue_token(user.id, "browser", settings), max_age=settings.jwt_minutes * 60,
        httponly=True, secure=settings.app_env == "production", samesite="lax", path="/api/v1",
    )
    return user

@router.delete("/session", status_code=204)
def delete_session(request: Request, settings: AppSettings):
    require_browser_origin(request, settings)
    response = Response(status_code=204)
    response.delete_cookie(
        cookie_name, httponly=True, secure=settings.app_env == "production", samesite="lax", path="/api/v1",
    )
    return response
