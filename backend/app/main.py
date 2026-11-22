import logging
from time import monotonic
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import OperationalError
from starlette.exceptions import HTTPException

from app.api.v1.api import router
from app.api.dependencies import Database
from app.api.upload_limit import UploadLimit
from app.core.config import get_settings
from app.core.errors import ApiError
from app.core.rate_limit import AuthRateLimiter, SharedAuthRateLimiter
from app.db.session import session_factory
from app.services.worker_health import readiness

logger = logging.getLogger(__name__)

def error_response(status: int, code: str, message: str, details=None, headers=None):
    return JSONResponse(
        {"error": {"code": code, "message": message, "details": details or []}},
        status_code=status, headers=headers,
    )

def create_app() -> FastAPI:
    settings = get_settings()
    api = FastAPI(title="AI Career Copilot", version="0.9.0")
    api.state.auth_limiter = (SharedAuthRateLimiter(session_factory(), settings.jwt_secret.get_secret_value())
                             if settings.app_env == "production" else AuthRateLimiter())
    api.add_middleware(UploadLimit)
    api.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins, allow_credentials=True,
                       allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
                       allow_headers=["Authorization", "Content-Type", "X-CSRF-Protection"], expose_headers=["X-Request-ID"])
    api.include_router(router)

    @api.middleware("http")
    async def protect_private_responses(request: Request, call_next):
        request.state.request_id = uuid4().hex
        started = monotonic()
        response = await call_next(request)
        response.headers["X-Request-ID"] = request.state.request_id
        if request.url.path.startswith("/api/v1/"):
            response.headers["Cache-Control"] = "no-store"
            response.headers["X-Content-Type-Options"] = "nosniff"
        if response.status_code >= 500:
            logger.warning("request failed id=%s method=%s status=%s duration_ms=%d",
                           request.state.request_id, request.method, response.status_code, (monotonic() - started) * 1000)
        return response

    @api.exception_handler(HTTPException)
    async def http_error(_request: Request, exc: HTTPException):
        return error_response(exc.status_code, exc.code if isinstance(exc, ApiError) else f"HTTP_{exc.status_code}",
                              str(exc.detail), headers=exc.headers)

    @api.exception_handler(RequestValidationError)
    async def validation_error(_request: Request, exc: RequestValidationError):
        details = [{"field": ".".join(map(str, item["loc"][1:])), "type": item["type"]} for item in exc.errors()]
        return error_response(422, "VALIDATION_ERROR", "请检查输入内容是否符合要求", details)

    @api.exception_handler(OperationalError)
    async def database_error(_request: Request, _exc: OperationalError):
        return error_response(503, "DATABASE_UNAVAILABLE", "数据库暂时不可用，请稍后再试")

    @api.exception_handler(Exception)
    async def unexpected_error(request: Request, exc: Exception):
        request_id = getattr(request.state, "request_id", uuid4().hex)
        logger.error("request failed id=%s type=%s", request_id, type(exc).__name__)
        return error_response(500, "INTERNAL_ERROR", "服务暂时不可用，请稍后再试",
                              headers={"Cache-Control": "no-store", "X-Request-ID": request_id})

    @api.get("/health")
    def health():
        return {"status": "ok"}

    @api.get("/ready")
    def ready(db: Database):
        result = readiness(db, settings.worker_heartbeat_max_age)
        return JSONResponse(result, status_code=200 if result["status"] == "ready" else 503,
                            headers={"Cache-Control": "no-store"})

    return api
