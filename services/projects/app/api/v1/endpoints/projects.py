"""Projects, test runs, GitHub integration, and webhook endpoints."""

from fastapi import APIRouter, Depends, Request, Header, HTTPException, BackgroundTasks, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional
from datetime import datetime, timezone

from app.core.database import get_db
from app.schemas.project import (
    ProjectCreate, ProjectUpdate, ProjectResponse, ProjectListResponse,
    TestRunCreate, TestRunResponse, TestRunListResponse,
    TestCaseListResponse, ProjectStats,
    GitHubIntegrationCreate, GitHubIntegrationResponse,
)
from app.services.project_service import ProjectService
from app.services.github_service import GitHubWebhookService, verify_webhook_signature
from app.api.v1.deps import get_current_user, CurrentUser

router = APIRouter()


# ── Projects ──────────────────────────────────────────────────

@router.post("/orgs/{org_id}/projects", response_model=ProjectResponse, status_code=201, tags=["Projects"])
async def create_project(
    org_id: str,
    data: ProjectCreate,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a new project in an organization."""
    svc = ProjectService(db)
    project = await svc.create(data, org_id=org_id, user_id=current_user["sub"])
    return project


@router.get("/orgs/{org_id}/projects", response_model=ProjectListResponse, tags=["Projects"])
async def list_projects(
    org_id: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    project_type: Optional[str] = None,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all projects for an organization."""
    svc = ProjectService(db)
    projects, total = await svc.list(org_id, page, page_size, project_type)
    return {"projects": projects, "total": total, "page": page, "page_size": page_size}


@router.get("/orgs/{org_id}/projects/{project_id}", response_model=ProjectResponse, tags=["Projects"])
async def get_project(
    org_id: str,
    project_id: str,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    svc = ProjectService(db)
    project = await svc.get(project_id, org_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


@router.patch("/orgs/{org_id}/projects/{project_id}", response_model=ProjectResponse, tags=["Projects"])
async def update_project(
    org_id: str,
    project_id: str,
    data: ProjectUpdate,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    svc = ProjectService(db)
    return await svc.update(project_id, org_id, data)


@router.delete("/orgs/{org_id}/projects/{project_id}", status_code=204, tags=["Projects"])
async def delete_project(
    org_id: str,
    project_id: str,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    svc = ProjectService(db)
    await svc.delete(project_id, org_id)


@router.get("/orgs/{org_id}/stats", response_model=ProjectStats, tags=["Dashboard"])
async def get_org_stats(
    org_id: str,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Dashboard statistics for an organization."""
    svc = ProjectService(db)
    return await svc.get_stats(org_id)


# ── GitHub Integration ────────────────────────────────────────

@router.post("/orgs/{org_id}/projects/{project_id}/github",
             response_model=GitHubIntegrationResponse, status_code=201, tags=["GitHub"])
async def connect_github(
    org_id: str,
    project_id: str,
    data: GitHubIntegrationCreate,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Connect a GitHub repository to a project."""
    svc = ProjectService(db)
    return await svc.connect_github(project_id, org_id, data)


# ── GitHub Webhook ────────────────────────────────────────────

@router.post("/webhooks/github", tags=["GitHub"], status_code=200)
async def github_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    x_github_event: Optional[str] = Header(None),
    x_hub_signature_256: Optional[str] = Header(None),
    db: AsyncSession = Depends(get_db),
):
    """GitHub webhook receiver — handles push and pull_request events."""
    body = await request.body()

    # Verify signature
    if x_hub_signature_256:
        if not verify_webhook_signature(body, x_hub_signature_256):
            raise HTTPException(status_code=401, detail="Invalid webhook signature")

    payload = await request.json()
    event = x_github_event or ""

    svc = GitHubWebhookService(db)

    if event == "push":
        background_tasks.add_task(svc.handle_push, payload)
    elif event == "pull_request":
        background_tasks.add_task(svc.handle_pull_request, payload)
    elif event == "ping":
        return {"message": "Webhook connected successfully"}

    return {"message": f"Event '{event}' received"}


# ── Test Runs ─────────────────────────────────────────────────

@router.post("/orgs/{org_id}/projects/{project_id}/runs",
             response_model=TestRunResponse, status_code=201, tags=["Test Runs"])
async def create_test_run(
    org_id: str,
    project_id: str,
    background_tasks: BackgroundTasks,
    data: Optional[TestRunCreate] = None,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Manually trigger a test run for a project."""
    if not data:
        data = TestRunCreate(project_id=project_id)
    data.project_id = project_id

    svc = ProjectService(db)
    run = await svc.create_run(project_id, org_id, current_user["sub"], data)

    # Trigger pipeline in background
    background_tasks.add_task(svc.trigger_run_pipeline, run.id)

    return run


@router.get("/orgs/{org_id}/projects/{project_id}/runs",
            response_model=TestRunListResponse, tags=["Test Runs"])
async def list_test_runs(
    org_id: str,
    project_id: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status_filter: Optional[str] = Query(None, alias="status"),
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    svc = ProjectService(db)
    runs, total = await svc.list_runs(project_id, org_id, page, page_size, status_filter)
    return {"runs": runs, "total": total, "page": page, "page_size": page_size}


@router.get("/orgs/{org_id}/runs/{run_id}", response_model=TestRunResponse, tags=["Test Runs"])
async def get_test_run(
    org_id: str,
    run_id: str,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    svc = ProjectService(db)
    run = await svc.get_run(run_id, org_id)
    if not run:
        raise HTTPException(status_code=404, detail="Test run not found")
    return run


@router.post("/orgs/{org_id}/runs/{run_id}/cancel",
             response_model=TestRunResponse, tags=["Test Runs"])
async def cancel_test_run(
    org_id: str,
    run_id: str,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    svc = ProjectService(db)
    from app.models.project import TestRunStatus
    return await svc.update_run_status(run_id, TestRunStatus.CANCELLED)


@router.get("/orgs/{org_id}/runs/{run_id}/cases",
            response_model=TestCaseListResponse, tags=["Test Cases"])
async def get_run_cases(
    org_id: str,
    run_id: str,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    svc = ProjectService(db)
    cases = await svc.get_run_cases(run_id, org_id)
    return {"cases": cases, "total": len(cases)}


@router.get("/orgs/{org_id}/export")
async def export_org_data(
    org_id: str,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    GDPR Article 20 — Data portability export.
    Returns all the org's projects, runs, and test cases as JSON.
    """
    from fastapi.responses import StreamingResponse
    import json, io

    svc = ProjectService(db)
    projects_data, _ = await svc.list(org_id=org_id, page=1, page_size=500)

    export = {
        "org_id": org_id,
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "schema_version": "1.0",
        "projects": [],
    }

    for project in projects_data:
        runs, _ = await svc.list_runs(project.id, org_id, page=1, page_size=1000)
        proj_export = {
            "id": project.id,
            "name": project.name,
            "url": project.project_url,
            "type": project.project_type,
            "created_at": project.created_at.isoformat() if project.created_at else None,
            "runs": [
                {
                    "id": r.id,
                    "status": r.status,
                    "total_tests": r.total_tests,
                    "passed_tests": r.passed_tests,
                    "failed_tests": r.failed_tests,
                    "created_at": r.created_at.isoformat() if r.created_at else None,
                }
                for r in runs
            ],
        }
        export["projects"].append(proj_export)

    content = json.dumps(export, indent=2)
    return StreamingResponse(
        io.BytesIO(content.encode()),
        media_type="application/json",
        headers={"Content-Disposition": f"attachment; filename=jarviis_export_{org_id[:8]}.json"},
    )
