"""JarviisAI — AI Orchestrator Service"""

import os
from contextlib import asynccontextmanager
from fastapi import FastAPI, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List
import logging
from app.core.logging_config import configure_logging

from app.core.config import settings
from app.services.test_generator import orchestrator
from app.core.metrics import setup_metrics
import asyncio
import httpx
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s"
)

logging.getLogger("httpx").setLevel(logging.ERROR)
logging.getLogger("httpcore").setLevel(logging.ERROR)
logger = logging.getLogger("jarviis.ai")
EVENTS_URL = os.getenv("EVENTS_SERVICE_URL", "http://jarviis-events:8017")
EXECUTOR_URL = os.getenv("EXECUTOR_SERVICE_URL", "http://jarviis-test-executor:8005")


@asynccontextmanager
async def lifespan(app: FastAPI):
    asyncio.create_task(event_consumer())
    logger.info(f"AI Orchestrator ready — primary: {settings.PRIMARY_MODEL}")
    yield


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
async def event_consumer():
    await asyncio.sleep(10)

    last_stream_id = None

    while True:
        try:
            print("EVENT CONSUMER RUNNING")

            async with httpx.AsyncClient(timeout=30.0) as client:

                response = await client.get(
                    f"{EVENTS_URL}/api/v1/events"
                )

                events = response.json().get("events", [])

                if not events:
                    await asyncio.sleep(5)
                    continue

                latest_event = events[-1]

                print("LATEST EVENT:", latest_event)

                if latest_event.get("event") != "test.started":
                    await asyncio.sleep(5)
                    continue

                payload = latest_event.get("payload", {})
                run_id = payload.get("run_id")

                if not run_id:
                    await asyncio.sleep(5)
                    continue

                stream_id = latest_event.get("_stream_id")

                if stream_id == last_stream_id:
                    await asyncio.sleep(5)
                    continue
                last_stream_id = stream_id

                print("Triggering executor for:", run_id)

                await client.post(
                    f"{EXECUTOR_URL}/api/v1/execute",
                    json={
                        "run_id": run_id,
                        "project_id": latest_event.get("project_id"),
                        "org_id": latest_event.get("org_id"),
                        "url": "https://example.com",
                        "test_suites": [
                            {
                                "name": "Smoke Test",
                                "tests": [
                                    {
                                        "name": "Homepage Test",
                                        "steps": [
                                            {
                                                "action": "goto",
                                                "value": "https://example.com"
                                            }
                                        ]
                                    }
                                ]
                            }
                        ]
                    
                    }
                
                )


        except Exception as e:
            print("Orchestrator Error:", e)

        await asyncio.sleep(5)

app = FastAPI(title="JarviisAI AI Orchestrator", version="1.0.0", lifespan=lifespan)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(CORSMiddleware, allow_origins=INTERNAL_ORIGINS, allow_credentials=True, allow_methods=["*"], allow_headers=["*"])


class GenerateRequest(BaseModel):
    run_id: str
    project_id: str
    org_id: str
    url: str
    project_type: str = "web"
    browsers: List[str] = ["chromium"]
    crawl_result: dict


setup_metrics(app, service_name="ai_orchestrator")


@app.get("/health")
async def health():
    return {
        "service": "ai-orchestrator",
        "status": "ok",
        "primary_model": settings.PRIMARY_MODEL,
        "fallback_model": settings.FALLBACK_MODEL,
        "anthropic_configured": bool(settings.ANTHROPIC_API_KEY),
        "openai_configured": bool(settings.OPENAI_API_KEY),
    }


@app.post("/api/v1/generate/tests", status_code=202)
async def generate_tests(data: GenerateRequest, background_tasks: BackgroundTasks):
    """Accept a crawl result and generate tests asynchronously."""
    background_tasks.add_task(orchestrator.run, data.model_dump())
    return {"message": "Test generation started", "run_id": data.run_id}


@app.post("/api/v1/generate/tests/sync")
async def generate_tests_sync(data: GenerateRequest):
    """Synchronous generation — for testing/debugging only."""
    from app.services.test_generator import TestGenerationService
    svc = TestGenerationService()
    result = await svc.generate(data.model_dump())
    return result
