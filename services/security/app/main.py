"""JarviisAI — Security Scanning Service"""

import os
from contextlib import asynccontextmanager
from fastapi import FastAPI, BackgroundTasks, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
import logging, os, httpx
from app.core.logging_config import configure_logging

from app.services.scanner import scanner, SecurityFinding
from app.core.metrics import setup_metrics

logging.basicConfig(level=os.getenv("LOG_LEVEL","info").upper(),
                    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s")
logger = logging.getLogger("jarviis.security")

PROJECTS_SERVICE_URL = os.getenv("PROJECTS_SERVICE_URL","http://projects:8002")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("🛡️ Security Scanner ready")
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

app = FastAPI(title="JarviisAI Security Scanner", version="1.0.0", lifespan=lifespan)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(CORSMiddleware, allow_origins=INTERNAL_ORIGINS, allow_credentials=True, allow_methods=["*"], allow_headers=["*"])


class ScanRequest(BaseModel):
    scan_id: str
    project_id: str
    org_id: str
    url: str
    depth: str = "standard"   # quick | standard | deep
    auth_config: Optional[dict] = None


setup_metrics(app, service_name="security")


@app.get("/health")
async def health():
    return {"service": "security-scanner", "status": "ok"}


@app.post("/api/v1/security/scan", status_code=202)
async def trigger_scan(data: ScanRequest, background_tasks: BackgroundTasks):
    background_tasks.add_task(_run_scan, data)
    return {"message": "Security scan started", "scan_id": data.scan_id}


@app.post("/api/v1/security/scan/sync")
async def trigger_scan_sync(data: ScanRequest):
    """Synchronous scan — for debugging."""
    result = await scanner.scan(data.url, data.scan_id, data.auth_config, data.depth)
    return _format_result(result)


async def _run_scan(data: ScanRequest) -> None:
    try:
        result = await scanner.scan(data.url, data.scan_id, data.auth_config, data.depth)
        formatted = _format_result(result)

        async with httpx.AsyncClient(timeout=15.0) as client:
            await client.post(
                f"{PROJECTS_SERVICE_URL}/api/v1/internal/runs/{data.scan_id}/security-result",
                json=formatted,
            )
    except Exception as e:
        logger.error(f"Security scan failed: {e}", exc_info=True)


def _format_result(result) -> dict:
    return {
        "scan_id": result.scan_id,
        "target_url": result.target_url,
        "score": result.score,
        "grade": result.grade,
        "total_checks": result.total_checks,
        "duration_seconds": result.duration_seconds,
        "errors": result.errors,
        "findings": [
            {
                "severity": f.severity,
                "category": f.category,
                "title": f.title,
                "description": f.description,
                "url": f.url,
                "evidence": f.evidence,
                "remediation": f.remediation,
                "owasp": f.owasp,
                "cwe": f.cwe,
            }
            for f in result.findings
        ],
        "summary": {
            "critical": sum(1 for f in result.findings if f.severity == "critical"),
            "high": sum(1 for f in result.findings if f.severity == "high"),
            "medium": sum(1 for f in result.findings if f.severity == "medium"),
            "low": sum(1 for f in result.findings if f.severity == "low"),
            "info": sum(1 for f in result.findings if f.severity == "info"),
        },
    }
