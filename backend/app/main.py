"""FastAPI application entrypoint.

Wires CORS, the aggregated API router, startup checks (pgcrypto extension, safe
LLM configuration) and one JSON error shape for the whole API.
"""
import logging

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.router import api_router
from app.config import settings
from app.database import ensure_pgcrypto_extension
from app.llm import UnsafeLLMConfigurationError, get_early_agent_llm_provider

logging.basicConfig(level=logging.DEBUG if settings.DEBUG else logging.INFO)
logger = logging.getLogger("sentinelx")

app = FastAPI(
    title=settings.PROJECT_NAME,
    description=(
        "SentinelX: vulnerability management for web infrastructure. Automated "
        "scanning, AI-assisted validation, vendor accountability and "
        "deadline-enforced remediation tracking."
    ),
    version="0.1.0",
    docs_url="/docs" if settings.DEBUG else None,
    redoc_url="/redoc" if settings.DEBUG else None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router)


@app.on_event("startup")
def on_startup() -> None:
    ensure_pgcrypto_extension()

    # Fail at startup, not on the first scan, if the early agents are set to
    # use the hosted model.
    try:
        get_early_agent_llm_provider()
    except UnsafeLLMConfigurationError as exc:
        logger.error(str(exc))
        raise


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    # Starlette's class, so errors raised by the router itself (404, 405) get
    # the same shape as ours. Headers such as WWW-Authenticate and Retry-After
    # are passed through.
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": {"message": exc.detail, "status_code": exc.status_code}},
        headers=getattr(exc, "headers", None),
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    # Never send stack traces or raw error text to the client. Log them instead.
    logger.exception("Unhandled exception processing request: %s %s", request.method, request.url)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"error": {"message": "An internal error occurred.", "status_code": 500}},
    )


@app.get("/health", tags=["health"])
def health_check() -> dict:
    return {"status": "ok", "environment": settings.ENVIRONMENT}