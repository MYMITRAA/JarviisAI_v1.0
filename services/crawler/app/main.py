"""JarviisAI — Crawler Service"""

import os
from contextlib import asynccontextmanager
from fastapi import FastAPI, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List
import httpx
import logging
from app.core.logging_config import configure_logging
import asyncio

from app.core.config import settings
from app.services.crawler_engine import CrawlerEngine
from app.core.metrics import setup_metrics

logging.basicConfig(level=getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO),
                    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s")
logger = logging.getLogger("jarviis.crawler")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("🚀 Crawler Service ready")
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

app = FastAPI(title="JarviisAI Crawler Service", version="1.0.0", lifespan=lifespan)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(CORSMiddleware, allow_origins=INTERNAL_ORIGINS, allow_credentials=True, allow_methods=["*"], allow_headers=["*"])


class CrawlRequest(BaseModel):
    run_id: str
    project_id: str
    org_id: str
    url: str
    project_type: str = "web"
    test_config: dict = {}
    browsers: List[str] = ["chromium"]
    auth_config: Optional[dict] = None
    max_depth: Optional[int] = None
    max_pages: Optional[int] = None


setup_metrics(app, service_name="crawler")


@app.get("/health")
async def health():
    return {"service": "crawler", "status": "ok"}


@app.post("/api/v1/crawl/start")
async def start_crawl(data: CrawlRequest, background_tasks: BackgroundTasks):
    """Accept a crawl job and process it in the background."""
    background_tasks.add_task(_run_crawl, data)
    return {"message": "Crawl started", "run_id": data.run_id}


async def _run_crawl(data: CrawlRequest) -> None:
    """
    Full crawl + notify pipeline:
    1. Update run status → CRAWLING
    2. Run Playwright crawler
    3. POST crawl result to AI Orchestrator
    4. On error: update run status → ERROR
    """
    logger.info(f"Starting crawl for run {data.run_id} — URL: {data.url}")

    # 1. Update status to CRAWLING
    await _update_run_status(data.run_id, "crawling", stage="crawling")

    try:
        engine = CrawlerEngine()
        result = await engine.crawl(
            url=data.url,
            max_depth=data.max_depth or settings.MAX_CRAWL_DEPTH,
            max_pages=data.max_pages or settings.MAX_PAGES_PER_CRAWL,
            auth_config=data.test_config.get("auth"),
            timeout_seconds=settings.CRAWL_TIMEOUT_SECONDS,
        )

        logger.info(
            f"Crawl complete for run {data.run_id}: "
            f"{result.pages_crawled} pages, {result.element_count} elements, "
            f"{result.crawl_duration_ms}ms"
        )

        # 2. Hand off to AI Orchestrator
        await _send_to_ai_orchestrator(data, result)

    except asyncio.TimeoutError:
        logger.error(f"Crawl timeout for run {data.run_id}")
        await _update_run_status(data.run_id, "error", error="Crawl timed out after 120 seconds", stage="crawl")

    except Exception as e:
        logger.error(f"Crawl error for run {data.run_id}: {e}", exc_info=True)
        await _update_run_status(data.run_id, "error", error=str(e), stage="crawl")


async def _send_to_ai_orchestrator(data: CrawlRequest, crawl_result) -> None:
    """Forward crawl result to AI Orchestrator for test generation."""
    payload = {
        "run_id": data.run_id,
        "project_id": data.project_id,
        "org_id": data.org_id,
        "url": data.url,
        "project_type": data.project_type,
        "browsers": data.browsers,
        "crawl_result": {
            "base_url": crawl_result.base_url,
            "pages_crawled": crawl_result.pages_crawled,
            "pages": crawl_result.pages,
            "sitemap": crawl_result.sitemap,
            "element_count": crawl_result.element_count,
            "form_count": crawl_result.form_count,
            "app_framework": crawl_result.app_framework,
            "app_context": crawl_result.app_context,
            "errors": crawl_result.errors,
        },
    }

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                f"{settings.AI_ORCHESTRATOR_URL}/api/v1/generate/tests",
                json=payload,
            )
            if resp.status_code not in (200, 202):
                logger.error(f"AI orchestrator rejected payload: {resp.status_code} {resp.text}")
                await _update_run_status(data.run_id, "error", error="AI orchestrator error", stage="generate")
    except Exception as e:
        logger.error(f"Failed to reach AI orchestrator: {e}")
        await _update_run_status(data.run_id, "error", error=f"Cannot reach AI orchestrator: {e}", stage="generate")


async def _update_run_status(
    run_id: str, status: str, error: Optional[str] = None, stage: Optional[str] = None
) -> None:
    """Notify Projects service of run status change."""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            print(settings.internal_service_secret)
            import asyncio
            await asyncio.sleep(2)
            response = await client.request(
                method="PATCH",
                url=f"{settings.PROJECTS_SERVICE_URL}/api/v1/internal/runs/{run_id}/status",
                json={
                    "status": status,
                    "error_message": error,
                    "error_stage": stage
                },
                headers={
                    "x-Internal-Secret": settings.internal_service_secret
                }
            )

            print("PATCH RESPONSE:", response.status_code, response.text)
    except Exception as e:
        logger.warning(f"Could not update run status: {e}")
