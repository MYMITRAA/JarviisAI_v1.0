"""JarviisAI — Mobile Testing Service (Android + iOS)"""

import os
from contextlib import asynccontextmanager
from fastapi import FastAPI, BackgroundTasks, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List
import logging, os, httpx
from app.core.logging_config import configure_logging

from app.services.mobile_orchestrator import mobile_orchestrator
from app.core.metrics import setup_metrics

logging.basicConfig(level=os.getenv("LOG_LEVEL","info").upper(),
                    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s")
logger = logging.getLogger("jarviis.mobile")

PROJECTS_SERVICE_URL = os.getenv("PROJECTS_SERVICE_URL","http://projects:8002")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("📱 Mobile Testing Service ready (Android + iOS)")
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

app = FastAPI(title="JarviisAI Mobile Testing", version="1.0.0", lifespan=lifespan)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(CORSMiddleware, allow_origins=INTERNAL_ORIGINS, allow_credentials=True, allow_methods=["*"], allow_headers=["*"])


class MobileRunRequest(BaseModel):
    run_id: str
    project_id: str
    org_id: str
    platform: str   # "android" | "ios"
    app_url: str    # APK/IPA URL
    device_name: Optional[str] = None
    os_version: Optional[str] = None
    test_type: str = "smoke"


class GenerateTestsRequest(BaseModel):
    platform: str
    app_description: str
    app_package: Optional[str] = None
    screens: Optional[List[str]] = None


setup_metrics(app, service_name="mobile")


@app.get("/health")
async def health():
    return {
        "service": "mobile-tester",
        "status": "ok",
        "android": bool(os.getenv("AWS_ACCESS_KEY_ID")),
        "ios": bool(os.getenv("BROWSERSTACK_USERNAME")),
    }


@app.post("/api/v1/mobile/run", status_code=202)
async def run_mobile_tests(data: MobileRunRequest, background_tasks: BackgroundTasks):
    background_tasks.add_task(_run_mobile, data)
    return {"message": f"Mobile {data.platform} test run started", "run_id": data.run_id}


@app.post("/api/v1/mobile/generate-tests")
async def generate_tests(data: GenerateTestsRequest):
    code = await mobile_orchestrator.generate_appium_tests(
        platform=data.platform,
        app_description=data.app_description,
        app_package=data.app_package,
        screens=data.screens,
    )
    return {"platform": data.platform, "test_code": code}


async def _run_mobile(data: MobileRunRequest) -> None:
    try:
        if data.platform == "android":
            result = await mobile_orchestrator.run_android(data.run_id, data.app_url)
        elif data.platform == "ios":
            result = await mobile_orchestrator.run_ios(data.run_id, data.app_url)
        else:
            logger.error(f"Unknown platform: {data.platform}")
            return

        async with httpx.AsyncClient(timeout=15.0) as client:
            await client.post(
                f"{PROJECTS_SERVICE_URL}/api/v1/internal/runs/{data.run_id}/complete",
                json={
                    "status": result.status,
                    "passed_tests": result.passed,
                    "failed_tests": result.failed,
                    "skipped_tests": 0,
                    "total_tests": result.total_tests,
                    "duration_seconds": result.duration_seconds,
                    "test_cases": result.test_results,
                },
            )
    except Exception as e:
        logger.error(f"Mobile run error: {e}", exc_info=True)
