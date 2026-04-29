"""JarviisAI — Global Search & Universal Filters"""

import os
from contextlib import asynccontextmanager
from fastapi import FastAPI, Query, Header
from fastapi.middleware.cors import CORSMiddleware
from typing import Optional, List
import logging, os, httpx
from app.core.logging_config import configure_logging
from datetime import datetime, timezone, timedelta

logging.basicConfig(level=os.getenv("LOG_LEVEL", "info").upper(),
                    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s")
logger = logging.getLogger("jarviis.search")

PROJECTS_URL = os.getenv("PROJECTS_SERVICE_URL", "http://projects:8002")
DEPLOY_URL = os.getenv("DEPLOY_SERVICE_URL", "http://deploy:8008")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("🔍 Search Service ready")
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

app = FastAPI(title="JarviisAI Search", version="1.0.0", lifespan=lifespan)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(CORSMiddleware, allow_origins=INTERNAL_ORIGINS, allow_credentials=True, allow_methods=["*"], allow_headers=["*"])


@app.get("/health")
async def health():
    return {"service": "search", "status": "ok"}

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



@app.get("/api/v1/search")
async def global_search(
    q: str = Query(..., min_length=2),
    org_id: str = Query(...),
    types: Optional[str] = Query(None, description="Comma-separated: projects,runs,deployments"),
    status: Optional[str] = Query(None),
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    limit: int = Query(20, ge=1, le=100),
    authorization: Optional[str] = Header(None),
):
    """Global search across all entity types."""
    headers = {"Authorization": authorization} if authorization else {}
    search_types = types.split(",") if types else ["projects", "runs", "deployments"]
    results = {"query": q, "results": [], "total": 0}
    q_lower = q.lower()

    async with httpx.AsyncClient(timeout=10.0) as client:
        # Search projects
        if "projects" in search_types:
            try:
                resp = await client.get(
                    f"{PROJECTS_URL}/api/v1/orgs/{org_id}/projects",
                    headers=headers, params={"page_size": 50}
                )
                if resp.status_code == 200:
                    for project in resp.json().get("projects", []):
                        name = (project.get("name", "") + " " + project.get("description", "") + " " + project.get("project_url", "")).lower()
                        if q_lower in name:
                            results["results"].append({
                                "type": "project",
                                "id": project["id"],
                                "title": project["name"],
                                "subtitle": project.get("project_url", ""),
                                "status": project.get("last_run_status"),
                                "url": f"/projects/{project['id']}",
                                "created_at": project.get("created_at"),
                            })
            except Exception:
                pass

        # Search runs
        if "runs" in search_types:
            try:
                params = {"page_size": 100}
                if status:
                    params["status_filter"] = status
                # Get all projects first to search their runs
                proj_resp = await client.get(
                    f"{PROJECTS_URL}/api/v1/orgs/{org_id}/projects",
                    headers=headers, params={"page_size": 20}
                )
                if proj_resp.status_code == 200:
                    for project in proj_resp.json().get("projects", [])[:5]:
                        runs_resp = await client.get(
                            f"{PROJECTS_URL}/api/v1/orgs/{org_id}/projects/{project['id']}/runs",
                            headers=headers, params=params
                        )
                        if runs_resp.status_code == 200:
                            for run in runs_resp.json().get("runs", []):
                                searchable = (
                                    run.get("git_branch", "") + " " +
                                    run.get("git_commit_sha", "") + " " +
                                    run.get("environment_name", "") + " " +
                                    run.get("id", "")
                                ).lower()
                                if q_lower in searchable or q_lower in project["name"].lower():
                                    results["results"].append({
                                        "type": "test_run",
                                        "id": run["id"],
                                        "title": f"Run #{run['id'][:8]} — {project['name']}",
                                        "subtitle": f"{run.get('status', '')} · {run.get('git_branch', '')}",
                                        "status": run.get("status"),
                                        "url": f"/projects/{project['id']}/runs/{run['id']}",
                                        "created_at": run.get("created_at"),
                                    })
            except Exception:
                pass

    # Apply date filters
    if date_from or date_to:
        filtered = []
        for r in results["results"]:
            created = r.get("created_at", "")
            if date_from and created < date_from:
                continue
            if date_to and created > date_to:
                continue
            filtered.append(r)
        results["results"] = filtered

    # Sort by date (most recent first) and limit
    results["results"].sort(key=lambda x: x.get("created_at", ""), reverse=True)
    results["results"] = results["results"][:limit]
    results["total"] = len(results["results"])
    return results
