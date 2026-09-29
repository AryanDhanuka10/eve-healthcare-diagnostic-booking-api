import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.routes import auth, bookings, centres, payments, tests, webhooks
from app.core.config import get_settings
from app.core.logging import configure_logging, request_id_ctx
from app.db.session import engine
from app.exceptions import AppError
from app.middleware import RequestContextMiddleware

logger = logging.getLogger(__name__)

DESCRIPTION = """
Backend for booking diagnostic tests and paying for them through a **simulated** payment provider.

* Authenticate: `POST /auth/signup`, then `POST /auth/login`, then click **Authorize** (username = email).
* No real payment gateway is used; `POST /payments/` runs a local simulator.
* Errors always look like `{"error": {"code", "message", "details?", "request_id"}}`.
"""

TAGS = [
    {"name": "Auth", "description": "Signup, login (JWT) and current user."},
    {"name": "Centres", "description": "Public reads; admin-only writes. Includes per-centre test prices."},
    {"name": "Tests", "description": "Diagnostic test types. Public reads; admin-only writes."},
    {"name": "Bookings", "description": "Owner-only access to bookings."},
    {"name": "Payments (simulated)", "description": "Simulated payment initiation."},
    {"name": "Webhooks", "description": "Signed, idempotent provider callbacks."},
    {"name": "Health", "description": "Liveness and readiness."},
]


def _error(
    request: Request, status_code: int, code: str, message: str, details=None, headers=None
) -> JSONResponse:
    body = {"code": code, "message": message, "request_id": request_id_ctx.get()}
    if details:
        body["details"] = details
    return JSONResponse({"error": body}, status_code=status_code, headers=headers)


def create_app() -> FastAPI:
    settings = get_settings()

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        configure_logging(settings.log_level)
        logger.info("startup", extra={"environment": settings.environment})
        yield

    app = FastAPI(
        title=settings.app_name,
        version="1.0.0",
        description=DESCRIPTION,
        openapi_tags=TAGS,
        lifespan=lifespan,
    )

    app.add_middleware(RequestContextMiddleware)
    if settings.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origins,
            allow_methods=["*"],
            allow_headers=["*"],
            allow_credentials=False,
        )

    @app.exception_handler(AppError)
    async def app_error_handler(request: Request, exc: AppError):
        level = logging.ERROR if exc.status_code >= 500 else logging.INFO
        logger.log(level, "app_error", extra={"code": exc.code, "status_code": exc.status_code})
        headers = (
            {"WWW-Authenticate": "Bearer"}
            if exc.status_code == 401 and exc.code != "INVALID_WEBHOOK_SIGNATURE"
            else None
        )
        status = 422 if exc.code == "INVALID_WEBHOOK_PAYLOAD" else exc.status_code
        return _error(request, status, exc.code, exc.message, exc.details, headers)

    @app.exception_handler(RequestValidationError)
    async def validation_handler(request: Request, exc: RequestValidationError):
        details = [
            {"loc": ".".join(map(str, e["loc"])), "msg": e["msg"], "type": e["type"]} for e in exc.errors()
        ]
        return _error(request, 422, "VALIDATION_ERROR", "Request validation failed", details)

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(request: Request, exc: StarletteHTTPException):
        code = {401: "AUTHENTICATION_FAILED", 404: "NOT_FOUND", 405: "METHOD_NOT_ALLOWED"}.get(
            exc.status_code, "HTTP_ERROR"
        )
        return _error(request, exc.status_code, code, str(exc.detail), headers=getattr(exc, "headers", None))

    @app.exception_handler(IntegrityError)
    async def integrity_handler(request: Request, exc: IntegrityError):
        # Constraint details stay in the logs; clients get a generic message.
        logger.error("integrity_error", exc_info=exc)
        return _error(request, 409, "DB_INTEGRITY_ERROR", "Request conflicts with existing data")

    @app.exception_handler(Exception)
    async def unhandled_handler(request: Request, exc: Exception):
        logger.error("unhandled_exception", exc_info=exc)
        return _error(request, 500, "INTERNAL_ERROR", "Internal server error")

    for r in (auth.router, centres.router, tests.router, bookings.router, payments.router, webhooks.router):
        app.include_router(r)

    @app.get("/health", tags=["Health"], summary="Liveness probe")
    def health():
        return {"status": "ok"}

    @app.get("/ready", tags=["Health"], summary="Readiness probe (checks the database)")
    def ready():
        try:
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
        except Exception:
            logger.exception("readiness_failed")
            return JSONResponse({"status": "unavailable"}, status_code=503)
        return {"status": "ready"}

    return app


app = create_app()
