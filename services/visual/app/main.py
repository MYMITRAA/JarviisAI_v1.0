"""JarviisAI — Visual Regression Service"""

import os
from contextlib import asynccontextmanager
from fastapi import FastAPI, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional
import httpx, logging, os

from app.services.visual_engine import visual_engine
from app.core.metrics import setup_metrics
from app.core.logging_config import configure_logging
configure_logging(service_name="visual", level=os.getenv("LOG_LEVEL", "INFO"))

logging.basicConfig(level=os.getenv("LOG_LEVEL","info").upper(),
                    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s")
logger = logging.getLogger("jarviis.visual")

PROJECTS_SERVICE_URL = os.getenv("PROJECTS_SERVICE_URL","http://projects:8002")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("📸 Visual Regression Service ready")
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

app = FastAPI(title="JarviisAI Visual Regression", version="1.0.0", lifespan=lifespan)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(CORSMiddleware, allow_origins=INTERNAL_ORIGINS, allow_credentials=True, allow_methods=["*"], allow_headers=["*"])


class VisualRunRequest(BaseModel):
    run_id: str
    project_id: str
    org_id: str
    urls: List[str]
    update_baselines: bool = False


class CompareRequest(BaseModel):
    project_id: str
    url: str
    screenshot_b64: str


setup_metrics(app, service_name="visual")


@app.get("/health")
async def health():
    return {"service": "visual-regression", "status": "ok"}


@app.post("/api/v1/visual/run", status_code=202)
async def run_visual(data: VisualRunRequest, background_tasks: BackgroundTasks):
    background_tasks.add_task(_run_visual, data)
    return {"message": "Visual regression started", "run_id": data.run_id}


@app.post("/api/v1/visual/compare")
async def compare_single(data: CompareRequest):
    result = visual_engine.compare(data.project_id, data.url, data.screenshot_b64)
    return {
        "url": result.url,
        "baseline_exists": result.baseline_exists,
        "diff_score": result.diff_score,
        "is_regression": result.is_regression,
        "message": result.message,
    }


@app.post("/api/v1/visual/baseline")
async def update_baseline(data: CompareRequest):
    baseline_id = visual_engine.save_baseline(data.project_id, data.url, data.screenshot_b64)
    return {"message": "Baseline saved", "baseline_id": baseline_id}


async def _run_visual(data: VisualRunRequest) -> None:
    try:
        results = await visual_engine.run_comparison(
            project_id=data.project_id,
            run_id=data.run_id,
            urls=data.urls,
            update_baselines=data.update_baselines,
        )

        regressions = [r for r in results if r.is_regression]
        async with httpx.AsyncClient(timeout=15.0) as client:
            await client.post(
                f"{PROJECTS_SERVICE_URL}/api/v1/internal/runs/{data.run_id}/visual-result",
                json={
                    "run_id": data.run_id,
                    "total_pages": len(results),
                    "regressions": len(regressions),
                    "results": [
                        {
                            "url": r.url, "diff_score": r.diff_score,
                            "is_regression": r.is_regression, "message": r.message,
                            "baseline_exists": r.baseline_exists,
                        }
                        for r in results
                    ],
                },
            )
    except Exception as e:
        logger.error(f"Visual regression failed for run {data.run_id}: {e}", exc_info=True)
