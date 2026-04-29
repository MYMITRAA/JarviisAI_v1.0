"""JarviisAI — Analytics Service"""

import os
from contextlib import asynccontextmanager
from fastapi import FastAPI, Query, Header
from fastapi.middleware.cors import CORSMiddleware
from typing import Optional
import logging, os
from app.core.logging_config import configure_logging

from app.services.analytics_service import analytics_service

logging.basicConfig(level=os.getenv("LOG_LEVEL", "info").upper(),
                    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logging.getLogger("jarviis.analytics").info("📈 Analytics Service ready")
    yield


APP_URL = os.getenv("APP_URL", "http://localhost:3000")
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

app = FastAPI(title="JarviisAI Analytics", version="1.0.0", lifespan=lifespan)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(CORSMiddleware, allow_origins=INTERNAL_ORIGINS, allow_credentials=True, allow_methods=["*"], allow_headers=["*"])


def _token(authorization: Optional[str] = Header(None)) -> str:
    return authorization.replace("Bearer ", "") if authorization else ""


@app.get("/health")
async def health():
    return {"service": "analytics", "status": "ok"}

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



@app.get("/api/v1/analytics/{org_id}/overview")
async def get_overview(
    org_id: str, days: int = Query(30, ge=7, le=365),
    authorization: Optional[str] = Header(None),
):
    return await analytics_service.get_overview(org_id, days=days, token=_token(authorization))


@app.get("/api/v1/analytics/{org_id}/reliability")
async def get_reliability(
    org_id: str,
    project_id: Optional[str] = Query(None),
    days: int = Query(30, ge=1, le=365),
    authorization: Optional[str] = Header(None),
):
    return await analytics_service.get_test_reliability(
        org_id, project_id=project_id, days=days, token=_token(authorization)
    )


@app.get("/api/v1/analytics/{org_id}/deployments")
async def get_deploy_metrics(
    org_id: str,
    project_id: Optional[str] = Query(None),
    days: int = Query(30, ge=1, le=365),
    authorization: Optional[str] = Header(None),
):
    return await analytics_service.get_deploy_metrics(
        org_id, project_id=project_id, days=days, token=_token(authorization)
    )


@app.get("/api/v1/analytics/{org_id}/security-trend")
async def get_security_trend(
    org_id: str, days: int = Query(30, ge=7, le=365),
    authorization: Optional[str] = Header(None),
):
    return await analytics_service.get_security_trend(org_id, days=days, token=_token(authorization))


@app.get("/api/v1/analytics/{org_id}/healing-roi")
async def get_healing_roi(
    org_id: str, days: int = Query(30, ge=1, le=365),
    authorization: Optional[str] = Header(None),
):
    return await analytics_service.get_healing_roi(org_id, days=days, token=_token(authorization))

@app.get("/api/v1/analytics/{org_id}/pass-rate-trend")
async def get_pass_rate_trend(
    org_id: str,
    days: int = Query(30, ge=7, le=365),
    project_id: Optional[str] = Query(None),
    authorization: Optional[str] = Header(None),
):
    return await analytics_service.get_pass_rate_trend(
        org_id, days=days, project_id=project_id, token=_token(authorization)
    )
