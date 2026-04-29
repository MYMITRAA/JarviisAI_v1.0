"""JarviisAI — Event Bus Service"""

import asyncio
import os
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List
import logging, os
from app.core.logging_config import configure_logging

from app.services.event_bus import event_bus, JarviisEvent
from app.services.trial_worker import trial_expiry_loop

logging.basicConfig(level=os.getenv("LOG_LEVEL", "info").upper(),
                    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s")
logger = logging.getLogger("jarviis.events")


@asynccontextmanager
async def lifespan(app: FastAPI):
    await event_bus.connect()
    # Start trial expiry background worker
    trial_task = asyncio.create_task(trial_expiry_loop())
    logger.info("🚌 Event Bus ready (trial expiry worker started)")
    yield
    trial_task.cancel()
    try:
        await trial_task
    except asyncio.CancelledError:
        pass
    await event_bus.disconnect()


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

app = FastAPI(title="JarviisAI Event Bus", version="1.0.0", lifespan=lifespan)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(CORSMiddleware, allow_origins=INTERNAL_ORIGINS, allow_credentials=True, allow_methods=["*"], allow_headers=["*"])


class PublishRequest(BaseModel):
    event: str
    org_id: Optional[str] = None
    project_id: Optional[str] = None
    actor_id: Optional[str] = None
    source_service: str = ""
    payload: dict = {}


@app.get("/health")
async def health():
    stats = await event_bus.get_stats()
    return {"service": "events", "status": "ok", "stream_length": stats.get("length", 0)}

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



@app.post("/api/v1/events/publish", status_code=202)
async def publish_event(data: PublishRequest):
    """Publish an event to the bus. Used by all services."""
    evt = JarviisEvent(**data.model_dump())
    entry_id = await event_bus.publish(evt)
    return {"entry_id": entry_id, "event": data.event}


@app.get("/api/v1/events")
async def get_events(
    org_id: Optional[str] = Query(None),
    event_types: Optional[str] = Query(None, description="Comma-separated event types"),
    since: Optional[str] = Query(None, description="Stream ID to start from"),
    limit: int = Query(50, ge=1, le=500),
):
    """Query the event stream."""
    types = event_types.split(",") if event_types else None
    events = await event_bus.get_events(org_id=org_id, event_types=types, since=since, limit=limit)
    return {"events": events, "count": len(events)}


@app.get("/api/v1/events/stats")
async def stream_stats():
    return await event_bus.get_stats()
