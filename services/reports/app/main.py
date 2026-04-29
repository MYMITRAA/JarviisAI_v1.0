"""JarviisAI — Reports Service (PDF + CSV + Scheduled)"""

import os
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Optional, List
import logging, os, json, io, csv
from app.core.logging_config import configure_logging
from datetime import datetime, timezone
import httpx

logging.basicConfig(level=os.getenv("LOG_LEVEL", "info").upper(),
                    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s")
logger = logging.getLogger("jarviis.reports")

ANALYTICS_URL = os.getenv("ANALYTICS_SERVICE_URL", "http://analytics:8020")
PROJECTS_URL = os.getenv("PROJECTS_SERVICE_URL", "http://projects:8002")
APP_URL = os.getenv("APP_URL", "https://jarviis.ai")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("📄 Reports Service ready")
    yield


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

app = FastAPI(title="JarviisAI Reports", version="1.0.0", lifespan=lifespan)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(CORSMiddleware, allow_origins=INTERNAL_ORIGINS, allow_credentials=True, allow_methods=["*"], allow_headers=["*"])


REPORT_TYPES = {
    "test_reliability":   "Test Reliability Report",
    "flaky_tests":        "Flaky Test Report",
    "deploy_stability":   "Deployment Stability Report",
    "security_risk":      "Security Risk Report",
    "usage_cost":         "Usage & Cost Report",
    "executive_summary":  "Executive Summary",
    "compliance_evidence":"Compliance Evidence Pack",
    "audit_access":       "Audit Access Report",
    "healing_effectiveness": "Healing Effectiveness Report",
    "sla_mttr":           "SLA / MTTR Report",
}


class ReportRequest(BaseModel):
    org_id: str
    report_type: str
    format: str = "csv"   # csv | json | pdf
    days: int = 30
    project_id: Optional[str] = None
    filters: dict = {}
    access_token: str = ""  # Bearer token for downstream API calls


@app.get("/health")
async def health():
    return {"service": "reports", "status": "ok", "report_types": list(REPORT_TYPES.keys())}

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



@app.get("/api/v1/reports/types")
async def list_report_types():
    return [{"id": k, "name": v} for k, v in REPORT_TYPES.items()]


@app.post("/api/v1/reports/generate")
async def generate_report(
    data: ReportRequest,
    background_tasks: BackgroundTasks,
    authorization: Optional[str] = Header(None),
):
    # Use token from body or header (header takes precedence)
    if authorization and not data.access_token:
        data.access_token = authorization.replace("Bearer ", "")
    """Generate a report in the requested format."""
    if data.report_type not in REPORT_TYPES:
        raise HTTPException(status_code=400, detail=f"Unknown report type: {data.report_type}")

    headers = {"Authorization": f"Bearer {data.access_token}"} if data.access_token else {}

    # Fetch analytics data
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(
                f"{ANALYTICS_URL}/api/v1/analytics/{data.org_id}/overview",
                headers=headers,
                params={"days": data.days},
            )
            analytics = resp.json() if resp.status_code == 200 else {}
    except Exception:
        analytics = {}

    # Build report data based on type
    report_data = _build_report_data(data.report_type, data.org_id, data.days, analytics)

    if data.format == "csv":
        return _csv_response(data.report_type, report_data)
    elif data.format == "json":
        return {
            "report_type": data.report_type,
            "report_name": REPORT_TYPES[data.report_type],
            "org_id": data.org_id,
            "period_days": data.days,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "data": report_data,
        }
    else:
        return _pdf_response(data.report_type, REPORT_TYPES[data.report_type], report_data, data.org_id, data.days)


def _build_report_data(report_type: str, org_id: str, days: int, analytics: dict) -> List[dict]:
    reliability = analytics.get("reliability", {})
    deploy = analytics.get("deployments", {})
    healing = analytics.get("healing", {})
    now = datetime.now(timezone.utc).isoformat()

    if report_type == "test_reliability":
        return [{
            "metric": "Total Runs", "value": reliability.get("total_runs", 0)
        }, {
            "metric": "Pass Rate", "value": f"{reliability.get('pass_rate', 0)}%"
        }, {
            "metric": "Failed Runs", "value": reliability.get("failed_runs", 0)
        }, {
            "metric": "Period", "value": f"Last {days} days"
        }, {
            "metric": "Generated", "value": now
        }]

    elif report_type == "deploy_stability":
        return [{
            "metric": "Total Deployments", "value": deploy.get("total_deployments", 0)
        }, {
            "metric": "Successful", "value": deploy.get("successful", 0)
        }, {
            "metric": "Rollbacks", "value": deploy.get("rollbacks", 0)
        }, {
            "metric": "Rollback Rate", "value": f"{deploy.get('rollback_rate', 0)}%"
        }, {
            "metric": "Avg Deploy Time", "value": f"{deploy.get('avg_deploy_seconds', 0)}s"
        }]

    elif report_type == "healing_effectiveness":
        return [{
            "metric": "Auto-Healed Tests", "value": healing.get("auto_healed_tests", 0)
        }, {
            "metric": "Healing Rate", "value": f"{healing.get('healing_rate_pct', 0)}%"
        }, {
            "metric": "Hours Saved", "value": healing.get("estimated_hours_saved", 0)
        }]

    elif report_type in ("executive_summary", "compliance_evidence"):
        return [
            {"section": "Testing", "metric": "Pass Rate", "value": f"{reliability.get('pass_rate', 0)}%"},
            {"section": "Testing", "metric": "Total Runs", "value": reliability.get("total_runs", 0)},
            {"section": "Deployment", "metric": "Total Deploys", "value": deploy.get("total_deployments", 0)},
            {"section": "Deployment", "metric": "Success Rate", "value": f"{100 - deploy.get('rollback_rate', 0)}%"},
            {"section": "Healing", "metric": "Auto-Healed", "value": healing.get("auto_healed_tests", 0)},
            {"section": "Meta", "metric": "Report Period", "value": f"Last {days} days"},
            {"section": "Meta", "metric": "Generated At", "value": now},
            {"section": "Meta", "metric": "Org ID", "value": org_id},
        ]

    return [{"metric": "Period", "value": f"Last {days} days"}, {"metric": "Generated", "value": now}]


def _csv_response(report_type: str, data: List[dict]) -> StreamingResponse:
    if not data:
        data = [{"message": "No data available"}]
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=list(data[0].keys()))
    writer.writeheader()
    writer.writerows(data)
    output.seek(0)
    filename = f"jarviis_{report_type}_{datetime.now().strftime('%Y%m%d')}.csv"
    return StreamingResponse(
        io.BytesIO(output.getvalue().encode()),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


def _pdf_response(report_type: str, report_name: str, data: List[dict], org_id: str, days: int):
    """Generate a simple PDF report using built-in HTML."""
    rows = "".join(
        f"<tr><td style='padding:8px;border-bottom:1px solid #2a2a4e'>{row.get('metric', row.get('section',''))}</td>"
        f"<td style='padding:8px;border-bottom:1px solid #2a2a4e;color:#a0a8c0'>{row.get('value','')}</td></tr>"
        for row in data
    )
    html = f"""<!DOCTYPE html><html><head><title>{report_name}</title></head>
<body style="font-family:sans-serif;background:#0a0a1a;color:#f0f2ff;padding:40px">
<h1 style="color:#6d28d9">{report_name}</h1>
<p style="color:#a0a8c0">Period: Last {days} days · Generated: {datetime.now().strftime('%Y-%m-%d %H:%M UTC')}</p>
<p style="color:#a0a8c0">Org: {org_id}</p>
<table style="width:100%;border-collapse:collapse;margin-top:20px">
<thead><tr><th style="text-align:left;padding:8px;background:#1a1a3e">Metric</th>
<th style="text-align:left;padding:8px;background:#1a1a3e">Value</th></tr></thead>
<tbody>{rows}</tbody></table>
<p style="color:#666;margin-top:40px;font-size:12px">Generated by JarviisAI · {APP_URL}</p>
</body></html>"""
    filename = f"jarviis_{report_type}_{datetime.now().strftime('%Y%m%d')}.html"
    return StreamingResponse(
        io.BytesIO(html.encode()),
        media_type="text/html",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )
