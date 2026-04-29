"""JarviisAI — Test Executor Service"""

from contextlib import asynccontextmanager
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional
import json
import logging
from app.core.logging_config import configure_logging
import os

import redis.asyncio as aioredis
from app.services.executor import executor
from app.core.metrics import setup_metrics

logging.basicConfig(level=os.getenv("LOG_LEVEL", "info").upper(),
                    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s")
logger = logging.getLogger("jarviis.executor")

REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/5")
redis_client: aioredis.Redis = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global redis_client
    redis_client = aioredis.from_url(REDIS_URL, encoding="utf-8", decode_responses=True)
    logger.info("🚀 Test Executor Service ready")
    yield
    await redis_client.close()


APP_URL = os.getenv("APP_URL", "http://localhost:3000")
INTERNAL_ORIGINS = [
    APP_URL,
    "http://localhost:3000",
    "http://jarviis-frontend:3000",
    "http://api-gateway:8000",
    "http://localhost:8000",
]


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

app = FastAPI(title="JarviisAI Test Executor", version="1.0.0", lifespan=lifespan)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(CORSMiddleware, allow_origins=INTERNAL_ORIGINS, allow_credentials=True, allow_methods=["*"], allow_headers=["*"])


class ExecuteRequest(BaseModel):
    run_id: str
    project_id: str
    org_id: str
    url: str
    browsers: List[str] = ["chromium"]
    test_suites: list
    test_plan: Optional[dict] = None


setup_metrics(app, service_name="test_executor")


@app.get("/health")
async def health():
    return {"service": "test-executor", "status": "ok"}


@app.post("/api/v1/execute", status_code=202)
async def execute_tests(data: ExecuteRequest, background_tasks: BackgroundTasks):
    """Accept a test suite and execute it asynchronously."""
    background_tasks.add_task(executor.execute, data.model_dump())
    return {"message": "Execution started", "run_id": data.run_id}


@app.websocket("/ws/runs/{run_id}")
async def websocket_run_events(websocket: WebSocket, run_id: str):
    """
    WebSocket endpoint — streams real-time test events for a run.
    Clients connect here to receive live pass/fail/log updates.
    """
    await websocket.accept()
    logger.info(f"WebSocket connected for run {run_id}")

    pubsub = redis_client.pubsub()
    channel = f"run:{run_id}:events"
    await pubsub.subscribe(channel)

    try:
        async for message in pubsub.listen():
            if message["type"] == "message":
                data = message["data"]
                await websocket.send_text(data)

                # Stop streaming when run completes
                try:
                    parsed = json.loads(data)
                    if parsed.get("event") == "complete":
                        break
                except Exception:
                    pass

    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected for run {run_id}")
    finally:
        await pubsub.unsubscribe(channel)
        await pubsub.close()
        logger.info(f"WebSocket cleanup done for run {run_id}")
