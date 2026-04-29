"""JarviisAI — Self-Healing Engine Service"""

import os
from contextlib import asynccontextmanager
from fastapi import FastAPI, BackgroundTasks, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List
import httpx
import logging
from app.core.logging_config import configure_logging

from app.core.config import settings
from app.services.healing_engine import healing_engine
from app.core.metrics import setup_metrics

logging.basicConfig(level=getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO),
                    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s")
logger = logging.getLogger("jarviis.healing")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("🔧 Self-Healing Service ready")
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

app = FastAPI(title="JarviisAI Self-Healing Engine", version="1.0.0", lifespan=lifespan)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(CORSMiddleware, allow_origins=INTERNAL_ORIGINS, allow_credentials=True, allow_methods=["*"], allow_headers=["*"])


class HealRequest(BaseModel):
    run_id: str
    project_id: str
    org_id: str
    project_url: str
    failed_cases: List[dict]
    dom_snapshots: Optional[dict] = None  # {page_url: [elements]}


class SelectorHealRequest(BaseModel):
    broken_selector: str
    dom_snapshot: List[dict]
    error_message: str = ""


setup_metrics(app, service_name="healing")


@app.get("/health")
async def health():
    return {
        "service": "healing",
        "status": "ok",
        "ai_configured": bool(settings.ANTHROPIC_API_KEY),
        "similarity_threshold": settings.SIMILARITY_THRESHOLD,
    }


@app.post("/api/v1/heal/run", status_code=202)
async def heal_run(data: HealRequest, background_tasks: BackgroundTasks):
    """Trigger async healing for all failed tests in a run."""
    background_tasks.add_task(_run_healing, data)
    return {"message": "Healing started", "run_id": data.run_id}


@app.post("/api/v1/heal/selector")
async def heal_selector(data: SelectorHealRequest):
    """Synchronous selector repair — for single-selector debugging."""
    from app.services.selector_repair import repair_model
    result = repair_model.repair(
        broken_selector=data.broken_selector,
        dom_snapshot=data.dom_snapshot,
        error_message=data.error_message,
        similarity_threshold=settings.SIMILARITY_THRESHOLD,
    )
    return {
        "original": result.original_selector,
        "repaired": result.repaired_selector,
        "confidence": result.confidence,
        "strategy": result.strategy,
        "healed": result.healed,
        "explanation": result.explanation,
        "top_candidates": [
            {"selector": c.selector, "confidence": c.confidence, "strategy": c.strategy}
            for c in result.candidates[:3]
        ],
    }


async def _run_healing(data: HealRequest) -> None:
    from dataclasses import asdict
    try:
        result = await healing_engine.heal_run(
            run_id=data.run_id,
            failed_cases=data.failed_cases,
            project_url=data.project_url,
            dom_snapshots=data.dom_snapshots,
        )

        # Report results back to Projects service
        async with httpx.AsyncClient(timeout=15.0) as client:
            await client.post(
                f"{settings.PROJECTS_SERVICE_URL}/api/v1/internal/runs/{data.run_id}/healing-result",
                json={
                    "run_id": result.run_id,
                    "auto_healed": result.auto_healed,
                    "needs_human": result.needs_human,
                    "healing_rate": result.healing_rate,
                    "attempts": result.attempts,
                },
            )
    except Exception as e:
        logger.error(f"Healing pipeline failed for run {data.run_id}: {e}", exc_info=True)
