"""JarviisAI — Usage Metering & Quota Enforcement Service"""

import os
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
import logging, os
from app.core.logging_config import configure_logging

from app.services.usage_service import usage_service, PLAN_LIMITS

logging.basicConfig(level=os.getenv("LOG_LEVEL", "info").upper(),
                    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s")
logger = logging.getLogger("jarviis.usage")


@asynccontextmanager
async def lifespan(app: FastAPI):
    await usage_service.connect()
    logger.info("📊 Usage Service ready")
    yield
    await usage_service.disconnect()


APP_URL = os.getenv("APP_URL", "http://localhost:3000")
INTERNAL_SECRET = os.getenv("INTERNAL_SERVICE_SECRET", "jarviis-internal-secret")
INTERNAL_ORIGINS = [
    APP_URL,
    "http://localhost:3000",
    "http://jarviis-frontend:3000",
    "http://api-gateway:8000",
    "http://localhost:8000",
]

from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

limiter = Limiter(key_func=get_remote_address, default_limits=["200/minute"])


class SecurityHeadersMiddleware:
    """Add security headers to every response."""
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_with_headers(message):
            if message["type"] == "http.response.start":
                headers = dict(message.get("headers", []))
                security_headers = [
                    (b"x-content-type-options", b"nosniff"),
                    (b"x-frame-options", b"DENY"),
                    (b"x-xss-protection", b"1; mode=block"),
                    (b"referrer-policy", b"strict-origin-when-cross-origin"),
                    (b"strict-transport-security", b"max-age=31536000; includeSubDomains"),
                ]
                existing = {h[0] for h in message.get("headers", [])}
                new_headers = list(message.get("headers", []))
                for h, v in security_headers:
                    if h not in existing:
                        new_headers.append((h, v))
                message = {**message, "headers": new_headers}
            await send(message)

        await self.app(scope, receive, send_with_headers)

app = FastAPI(title="JarviisAI Usage Service", version="1.0.0", lifespan=lifespan)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SecurityHeadersMiddleware)
INTERNAL_SECRET = os.getenv("INTERNAL_SERVICE_SECRET", "jarviis-internal-secret")

app.add_middleware(CORSMiddleware, allow_origins=INTERNAL_ORIGINS, allow_credentials=True, allow_methods=["*"], allow_headers=["*"])


class CheckRequest(BaseModel):
    org_id: str
    plan: str
    metric: str
    increment_by: int = 1


class TotalRequest(BaseModel):
    org_id: str
    metric: str
    value: Optional[int] = None
    delta: int = 1


@app.get("/health")
async def health():
    return {"service": "usage", "status": "ok"}

@app.get("/metrics", include_in_schema=False)
async def metrics():
    """Prometheus metrics endpoint."""
    try:
        from prometheus_client import generate_latest, CONTENT_TYPE_LATEST, REGISTRY
        from fastapi.responses import Response
        return Response(content=generate_latest(REGISTRY), media_type=CONTENT_TYPE_LATEST)
    except ImportError:
        from fastapi.responses import PlainTextResponse
        return PlainTextResponse("# prometheus_client not installed\n")



@app.post("/api/v1/usage/check")
async def check_usage(
    data: CheckRequest,
    x_internal_secret: Optional[str] = Header(None),
):
    """
    Check if operation is allowed and increment counter.
    Call this BEFORE starting any plan-limited operation.
    Returns {allowed, current, limit, remaining, warning}
    """
    if x_internal_secret != INTERNAL_SECRET:
        from fastapi import HTTPException
        raise HTTPException(status_code=403, detail="Internal service access only")
    return await usage_service.check_and_increment(
        org_id=data.org_id,
        plan=data.plan,
        metric=data.metric,
        increment_by=data.increment_by,
    )


@app.get("/api/v1/usage/{org_id}")
async def get_usage(org_id: str, plan: str = "starter"):
    """Get full usage summary for an org — used by billing/dashboard."""
    return await usage_service.get_usage(org_id, plan)


@app.post("/api/v1/usage/total/increment")
async def increment_total(data: TotalRequest):
    """Increment a non-time-bounded counter (projects, members)."""
    new_val = await usage_service.increment_total(data.org_id, data.metric, data.delta)
    return {"org_id": data.org_id, "metric": data.metric, "value": new_val}


@app.post("/api/v1/usage/total/decrement")
async def decrement_total(data: TotalRequest):
    """Decrement a total counter (project deleted, member removed)."""
    new_val = await usage_service.decrement_total(data.org_id, data.metric, data.delta)
    return {"org_id": data.org_id, "metric": data.metric, "value": new_val}


@app.post("/api/v1/usage/{org_id}/reset")
async def reset_usage(org_id: str):
    """Reset monthly counters on billing renewal."""
    await usage_service.reset_monthly(org_id)
    return {"message": f"Monthly usage reset for org {org_id}"}


@app.get("/api/v1/usage/plans/limits")
async def get_plan_limits():
    """Return all plan limits — used by frontend for display."""
    return PLAN_LIMITS
