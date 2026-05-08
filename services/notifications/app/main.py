"""JarviisAI — Notifications Service"""

import asyncio
import json
import logging
from app.core.logging_config import configure_logging
import os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from datetime import datetime, timezone
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List
import redis.asyncio as aioredis

from app.services.notification_service import notification_service

logging.basicConfig(level=os.getenv("LOG_LEVEL", "info").upper(),
                    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s")
logger = logging.getLogger("jarviis.notifications")

REDIS_URL = os.getenv("REDIS_URL", "redis://:redis_secret@redis:6379/17")

# Events this service listens for
SUBSCRIBED_EVENTS = [
    "test.failed", "test.completed",
    "deploy.rolled_back", "deploy.failed",
    "security.issue_critical",
    "usage.warning_80pct", "usage.limit_reached",
    "billing.trial_expired", "billing.payment_failed", "billing.plan_changed",
    "healing.applied",
]


async def event_consumer():
    """Subscribe to Redis pub/sub and dispatch notifications."""
    redis = aioredis.from_url(REDIS_URL, encoding="utf-8", decode_responses=True)
    pubsub = redis.pubsub()
    channels = [f"jarviis:events:{evt}" for evt in SUBSCRIBED_EVENTS]
    await pubsub.subscribe(*channels)
    logger.info(f"Notification consumer subscribed to {len(channels)} event channels")

    async for message in pubsub.listen():
        print("RAW REDIS MESSAGE:", message)
        if message["type"] != "message":
            continue
        try:
            data = json.loads(message["data"])
            print("NOTIFICATION EVENT DATA:", data)
            event_type = data.get("event", "")
            org_id = data.get("org_id", "")
            payload = data.get("payload", {})
            if isinstance(payload, str):
                payload = json.loads(payload)
            if org_id and event_type:
                await notification_service.handle_event(event_type, org_id, payload)
        except Exception as e:
            logger.error(f"Notification dispatch error: {e}", exc_info=True)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await notification_service.connect()
    # Start event consumer in background
    task = asyncio.create_task(event_consumer())
    logger.info("🔔 Notifications Service ready")
    yield
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
    await notification_service.disconnect()


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

app = FastAPI(title="JarviisAI Notifications", version="1.0.0", lifespan=lifespan)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(CORSMiddleware, allow_origins=INTERNAL_ORIGINS, allow_credentials=True, allow_methods=["*"], allow_headers=["*"])


class NotifConfigRequest(BaseModel):
    slack_webhook_url: Optional[str] = None
    teams_webhook_url: Optional[str] = None
    notification_email: Optional[str] = None
    custom_webhooks: List[str] = []
    enabled_events: List[str] = []


class MarkReadRequest(BaseModel):
    notification_id: str


@app.get("/health")
async def health():
    return {"service": "notifications", "status": "ok"}

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



@app.get("/api/v1/notifications/{org_id}")
async def get_notifications(org_id: str, limit: int = 50):
    notifications = await notification_service.get_in_app_notifications(org_id, limit)
    unread = await notification_service.get_unread_count(org_id)
    return {"notifications": notifications, "unread_count": unread}


@app.get("/api/v1/notifications/{org_id}/unread-count")
async def get_unread_count(org_id: str):
    count = await notification_service.get_unread_count(org_id)
    return {"unread_count": count}


@app.post("/api/v1/notifications/{org_id}/mark-read")
async def mark_read(org_id: str, data: MarkReadRequest):
    await notification_service.mark_read(org_id, data.notification_id)
    return {"message": "Marked as read"}


@app.get("/api/v1/notifications/{org_id}/config")
async def get_config(org_id: str):
    config = await notification_service._get_org_config(org_id)
    return config


@app.post("/api/v1/notifications/{org_id}/config")
async def save_config(org_id: str, data: NotifConfigRequest):
    await notification_service.save_org_config(org_id, data.model_dump())
    return {"message": "Notification config saved"}


@app.post("/api/v1/notifications/test-send")
async def test_send(org_id: str, event_type: str = "test.failed"):
    """Send a test notification to verify configuration."""
    await notification_service.handle_event(event_type, org_id, {
        "run_id": "test-run-id",
        "passed": 45, "failed": 5, "total": 50, "pass_rate": 90.0,
    })
    return {"message": f"Test notification sent for {event_type}"}


# ── Webhook Management ────────────────────────────────────────

class WebhookRegistration(BaseModel):
    org_id: str
    url: str
    events: List[str] = []  # empty = all events
    secret: Optional[str] = None  # for HMAC signature


class WebhookDelivery(BaseModel):
    webhook_id: str
    event: str
    status: str  # delivered | failed | pending
    attempts: int
    last_attempt_at: Optional[str]
    response_code: Optional[int]


@app.post("/api/v1/webhooks/register")
async def register_webhook(data: WebhookRegistration):
    """Register an outbound webhook endpoint."""
    import uuid, hashlib
    webhook_id = str(uuid.uuid4())
    secret = data.secret or hashlib.sha256(webhook_id.encode()).hexdigest()[:32]
    webhook = {
        "id": webhook_id,
        "org_id": data.org_id,
        "url": data.url,
        "events": data.events,
        "secret": secret,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "active": True,
    }
    redis_client = notification_service._redis
    if redis_client:
        await redis_client.set(
            f"webhook:reg:{data.org_id}:{webhook_id}",
            json.dumps(webhook),
            ex=86400 * 365
        )
        # Add to org's webhook list
        await redis_client.sadd(f"webhooks:{data.org_id}", webhook_id)
    return {"webhook_id": webhook_id, "secret": secret, "message": "Webhook registered"}


@app.get("/api/v1/webhooks/{org_id}")
async def list_webhooks(org_id: str):
    """List all registered webhooks for an org."""
    redis_client = notification_service._redis
    if not redis_client:
        return {"webhooks": []}
    webhook_ids = await redis_client.smembers(f"webhooks:{org_id}")
    webhooks = []
    for wid in webhook_ids:
        raw = await redis_client.get(f"webhook:reg:{org_id}:{wid}")
        if raw:
            w = json.loads(raw)
            w.pop("secret", None)  # Never return secret
            webhooks.append(w)
    return {"webhooks": webhooks}


@app.delete("/api/v1/webhooks/{org_id}/{webhook_id}")
async def delete_webhook(org_id: str, webhook_id: str):
    """Deactivate a webhook."""
    redis_client = notification_service._redis
    if redis_client:
        await redis_client.delete(f"webhook:reg:{org_id}:{webhook_id}")
        await redis_client.srem(f"webhooks:{org_id}", webhook_id)
    return {"deleted": True}


@app.get("/api/v1/webhooks/{org_id}/deliveries")
async def webhook_deliveries(org_id: str, limit: int = 50):
    """Get recent webhook delivery log for an org."""
    redis_client = notification_service._redis
    if not redis_client:
        return {"deliveries": []}
    items = await redis_client.lrange(f"webhook:deliveries:{org_id}", 0, limit - 1)
    return {"deliveries": [json.loads(i) for i in items]}
