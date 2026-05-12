"""JarviisAI — API Testing Engine"""

import os
from contextlib import asynccontextmanager
from fastapi import FastAPI, BackgroundTasks, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List
import logging, os
from app.core.logging_config import configure_logging

from app.services.spec_parser import parser
from app.services.api_runner import runner
from app.core.metrics import setup_metrics

logging.basicConfig(level=os.getenv("LOG_LEVEL","info").upper(),
                    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s")
logger = logging.getLogger("jarviis.api-tester")

PROJECTS_SERVICE_URL = os.getenv("PROJECTS_SERVICE_URL","http://projects:8002")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("🔌 API Testing Engine ready")
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

app = FastAPI(title="JarviisAI API Testing Engine", version="1.0.0", lifespan=lifespan)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(CORSMiddleware, allow_origins=INTERNAL_ORIGINS, allow_credentials=True, allow_methods=["*"], allow_headers=["*"])


class ImportSpecRequest(BaseModel):
    url: Optional[str] = None
    content: Optional[str] = None
    format: str = "openapi_3"
    name: str = "My API"
    base_url: Optional[str] = None


class RunApiTestsRequest(BaseModel):
    run_id: str
    project_id: str
    org_id: str
    spec_content: str
    spec_format: str = "openapi_3"
    base_url: str
    auth_config: Optional[dict] = None
    environment: str = "default"


setup_metrics(app, service_name="api_tester")


@app.get("/health")
async def health():
    return {"service": "api-tester", "status": "ok"}


@app.post("/api/v1/specs/parse")
async def parse_spec(data: ImportSpecRequest):
    """Parse and validate an API spec without running tests."""
    try:
        if data.url:
            spec = parser.parse_url(data.url)
        elif data.content:
            if data.format == "postman":
                spec = parser.parse_postman(data.content)
            else:
                spec = parser.parse_content(data.content)
        else:
            raise HTTPException(status_code=400, detail="Provide either url or content")

        return {
            "title": spec.title,
            "version": spec.version,
            "format": spec.format,
            "base_url": spec.base_url,
            "endpoint_count": len(spec.endpoints),
            "tags": spec.tags,
            "servers": spec.servers,
            "endpoints": [
                {
                    "method": ep.method,
                    "path": ep.path,
                    "summary": ep.summary,
                    "auth_required": ep.auth_required,
                    "deprecated": ep.deprecated,
                    "tags": ep.tags,
                }
                for ep in spec.endpoints
            ],
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Spec parse error: {str(e)}")


@app.post("/api/v1/tests/run", status_code=202)
async def run_tests(data: RunApiTestsRequest, background_tasks: BackgroundTasks):
    """Run API tests against a live API."""
    background_tasks.add_task(_execute_tests, data)
    return {"message": "API test run started", "run_id": data.run_id}


@app.post("/api/v1/tests/run/sync")
async def run_tests_sync(data: RunApiTestsRequest):
    """Synchronous run — for quick testing."""
    spec = parser.parse_content(data.spec_content)
    if data.base_url:
        spec.base_url = data.base_url
    return await runner.run(data.run_id, spec, data.base_url, data.auth_config, data.environment)


async def _execute_tests(data: RunApiTestsRequest) -> None:
    import httpx
    try:
        spec = parser.parse_content(data.spec_content)
        if data.base_url:
            spec.base_url = data.base_url

        result = await runner.run(
            run_id=data.run_id,
            spec=spec,
            base_url=data.base_url,
            auth_config=data.auth_config,
            environment=data.environment,
        )

        # Report to Projects service
        async with httpx.AsyncClient(timeout=15.0) as client:
            await client.post(
                f"{PROJECTS_SERVICE_URL}/api/v1/internal/runs/{data.run_id}/complete",
                json={
                    "status": result["status"],
                    "passed_tests": result["passed"],
                    "failed_tests": result["failed"],
                    "skipped_tests": 0,
                    "total_tests": result["total"],
                    "duration_seconds": 0,
                    "test_cases": [
                        {
                            "name": r["test_name"],
                            "status": r["status"],
                            "error_message": r.get("error_message"),
                            "duration_ms": r.get("response_time_ms"),
                        }
                        for r in result.get("results", [])
                    ],
                },
                headers={

                    "x-internal-secret": settings.internal_service_secret
                }

            )
    except Exception as e:
        logger.error(f"API test run failed: {e}", exc_info=True)
