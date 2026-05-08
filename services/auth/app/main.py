import os
"""
JarviisAI — Auth Service
Handles: Registration, Login, OAuth (GitHub/Google), JWT tokens,
         Email verification, Password reset, Organization management
"""

from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

from app.core.config import settings
from app.core.database import engine, Base
from app.core.redis import redis_client
from app.api.v1.router import api_router
from app.middleware.logging import LoggingMiddleware
from app.middleware.security import SecurityHeadersMiddleware
from app.core.metrics import setup_metrics
import logging
from app.core.logging_config import configure_logging

# ── Logging ──────────────────────────────────────────────────
logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO),
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger("jarviis.auth")

# ── Rate Limiter ─────────────────────────────────────────────
limiter = Limiter(key_func=get_remote_address, default_limits=["200/minute"])


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events."""
    logger.info("🚀 JarviisAI Auth Service starting up...")

    # Create DB tables (Alembic handles migrations in prod)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("✅ Database tables ready")

    # Test Redis connection
    await redis_client.ping()
    logger.info("✅ Redis connection established")

    yield

    # Shutdown
    await redis_client.close()
    await engine.dispose()
    logger.info("👋 Auth Service shut down cleanly")


# ── App Factory ──────────────────────────────────────────────
app = FastAPI(
    title="JarviisAI Auth Service",
    description="Authentication, authorization, and user management",
    version="1.0.0",
    docs_url="/docs" if settings.ENVIRONMENT == "development" else None,
    redoc_url="/redoc" if settings.ENVIRONMENT == "development" else None,
    lifespan=lifespan,
)

# ── Rate limiting ─────────────────────────────────────────────
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# ── Middleware (order matters — last added = first executed) ──
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(LoggingMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["*"],
    expose_headers=["X-Request-ID"],
)

# ── Routes ────────────────────────────────────────────────────
app.include_router(api_router, prefix="/api/v1")


# ── Health check ─────────────────────────────────────────────
setup_metrics(app, service_name="auth")


@app.get("/health", tags=["Health"])
async def health_check():
    """Service health endpoint — used by Docker healthcheck and load balancer."""
    try:
        await redis_client.ping()
        redis_status = "ok"
    except Exception:
        redis_status = "error"

    return {
        "service": "auth",
        "status": "ok",
        "version": "1.0.0",
        "redis": redis_status,
    }


# ── Global exception handler ─────────────────────────────────
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "An internal error occurred. Please try again."},
    )
@app.get("/health")
def health():
    return {"status": "ok"}
