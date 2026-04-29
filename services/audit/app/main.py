"""JarviisAI — Audit Service (Immutable Cross-Service Audit Trail)"""

import os
from contextlib import asynccontextmanager
from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List
import logging, os, json
from app.core.logging_config import configure_logging
from datetime import datetime, timezone, timedelta
import httpx
import asyncio
import redis.asyncio as aioredis

logging.basicConfig(level=os.getenv("LOG_LEVEL", "info").upper(),
                    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s")
logger = logging.getLogger("jarviis.audit")

REDIS_URL = os.getenv("REDIS_URL", "redis://:redis_secret@redis:6379/20")
EVENTS_SERVICE_URL = os.getenv("EVENTS_SERVICE_URL", "http://events:8017")

# All events get audit entries
AUDIT_EVENTS = [
    "test.started", "test.completed", "test.failed",
    "deploy.started", "deploy.completed", "deploy.rolled_back", "deploy.failed",
    "security.scan_completed", "security.issue_critical",
    "billing.plan_changed", "billing.trial_started", "billing.trial_expired",
    "org.member_added", "org.member_removed",
    "project.created", "project.deleted",
    "sso.login_success", "sso.login_failure",
    "healing.applied",
    "usage.limit_reached",
]

_redis: Optional[aioredis.Redis] = None


async def event_consumer():
    redis = aioredis.from_url(REDIS_URL, encoding="utf-8", decode_responses=True)
    pubsub = redis.pubsub()
    channels = [f"jarviis:events:{evt}" for evt in AUDIT_EVENTS]
    await pubsub.subscribe(*channels)
    logger.info(f"Audit consumer subscribed to {len(channels)} events")

    async for message in pubsub.listen():
        if message["type"] != "message":
            continue
        try:
            data = json.loads(message["data"])
            await _store_audit_entry(data)
        except Exception as e:
            logger.error(f"Audit store error: {e}")


async def _store_audit_entry(event: dict) -> None:
    if not _redis:
        return
    org_id = event.get("org_id", "system")
    entry = {
        "id": event.get("trace_id", ""),
        "event": event.get("event", ""),
        "org_id": org_id,
        "project_id": event.get("project_id"),
        "actor_id": event.get("actor_id"),
        "source": event.get("source_service", ""),
        "payload": event.get("payload", {}),
        "timestamp": event.get("timestamp", datetime.now(timezone.utc).isoformat()),
    }
    # Store in Redis sorted set (by timestamp score for range queries)
    score = datetime.now(timezone.utc).timestamp()
    await _redis.zadd(f"audit:{org_id}", {json.dumps(entry): score})
    # Trim to last 10,000 entries per org
    await _redis.zremrangebyrank(f"audit:{org_id}", 0, -10001)
    # 90-day TTL
    await _redis.expire(f"audit:{org_id}", 90 * 24 * 3600)


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _redis
    _redis = aioredis.from_url(REDIS_URL, encoding="utf-8", decode_responses=True)
    task = asyncio.create_task(event_consumer())
    logger.info("📋 Audit Service ready")
    yield
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
    if _redis:
        await _redis.aclose()


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

app = FastAPI(title="JarviisAI Audit Service", version="1.0.0", lifespan=lifespan)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SecurityHeadersMiddleware)
INTERNAL_SECRET = os.getenv("INTERNAL_SERVICE_SECRET", "jarviis-internal-secret")

app.add_middleware(CORSMiddleware, allow_origins=INTERNAL_ORIGINS, allow_credentials=True, allow_methods=["*"], allow_headers=["*"])


class AuditWriteRequest(BaseModel):
    event: str
    org_id: str
    actor_id: Optional[str] = None
    project_id: Optional[str] = None
    source: str = ""
    payload: dict = {}


@app.get("/health")
async def health():
    return {"service": "audit", "status": "ok"}

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



@app.post("/api/v1/audit/write")
async def write_audit(data: AuditWriteRequest):
    """Manually write an audit entry (for services that don't use the event bus)."""
    await _store_audit_entry(data.model_dump())
    return {"written": True}


@app.get("/api/v1/audit/{org_id}")
async def get_audit_log(
    org_id: str,
    event_type: Optional[str] = Query(None),
    actor_id: Optional[str] = Query(None),
    days: int = Query(30, ge=1, le=90),
    limit: int = Query(100, ge=1, le=500),
):
    """Query audit log for an org."""
    if not _redis:
        return {"entries": [], "total": 0}

    since_score = (datetime.now(timezone.utc) - timedelta(days=days)).timestamp()
    raw = await _redis.zrangebyscore(
        f"audit:{org_id}", since_score, "+inf",
        withscores=False, offset=0, count=limit * 2
    )

    entries = []
    for item in raw:
        try:
            entry = json.loads(item)
            if event_type and entry.get("event") != event_type:
                continue
            if actor_id and entry.get("actor_id") != actor_id:
                continue
            entries.append(entry)
            if len(entries) >= limit:
                break
        except Exception:
            pass

    # Most recent first
    entries.reverse()
    return {"entries": entries, "total": len(entries)}


@app.get("/api/v1/audit/{org_id}/export")
async def export_audit_log(org_id: str, days: int = Query(90, ge=1, le=90)):
    """Export full audit log as JSON — for compliance."""
    from fastapi.responses import StreamingResponse
    import io
    result = await get_audit_log(org_id, days=days, limit=10000)
    content = json.dumps(result, indent=2)
    return StreamingResponse(
        io.BytesIO(content.encode()),
        media_type="application/json",
        headers={"Content-Disposition": f"attachment; filename=audit_log_{org_id}_{days}d.json"},
    )
