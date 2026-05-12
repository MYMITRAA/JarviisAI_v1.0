"""
Internal endpoints — only called by other JarviisAI services.
NOT exposed through API gateway. Protected by service-to-service auth header.
"""

from fastapi import APIRouter, Depends, HTTPException, Header
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel
from typing import Optional, List
import os
from datetime import datetime, timezone


from app.core.database import get_db
from app.models.project import TestRunStatus, TestCase, TestRun
from app.services.project_service import ProjectService
from app.schemas.internal import CompleteRequest

router = APIRouter(prefix="/internal", tags=["Internal"])

INTERNAL_SECRET = os.getenv("INTERNAL_SERVICE_SECRET", "jarviis-internal-secret")


from fastapi import Request

def verify_internal(request: Request):
    
    print("CLIENT:", request.client)
    header = request.headers.get("X-Internal-Secret")
    print("HEADER:", header)
    print("EXPECTED:", INTERNAL_SECRET)

    if header != INTERNAL_SECRET:
        raise HTTPException(
            status_code=403,
            detail="Forbidden — internal endpoint"
        )


class StatusUpdateRequest(BaseModel):
    status: str
    error_message: Optional[str] = None
    error_stage: Optional[str] = None
    ai_summary: Optional[str] = None


class PlanUpdateRequest(BaseModel):
    ai_test_plan: dict
    crawl_summary: Optional[dict] = None


class HealingResultRequest(BaseModel):
    run_id: str
    auto_healed: int
    needs_human: int
    healing_rate: float
    attempts: List[dict]


class VisualResultRequest(BaseModel):
    run_id: str
    total_pages: int
    regressions: int
    results: List[dict]


class SecurityResultRequest(BaseModel):
    scan_id: str
    target_url: str
    score: int
    grade: str
    total_checks: int
    duration_seconds: float
    findings: List[dict]
    summary: dict
    errors: List[str] = []


@router.get("/runs/{run_id}/status")
async def get_run_status(
    run_id: str,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(verify_internal),
):
    """Called by Deploy service to check if a test run passed (test gate)."""
    run = await db.get(TestRun, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    return {
        "run_id": run_id,
        "status": run.status,
        "passed": run.status == "passed",
        "total_tests": run.total_tests,
        "passed_tests": run.passed_tests,
        "failed_tests": run.failed_tests,
        "pass_rate": run.pass_rate,
    }


@router.post("/runs/{run_id}/security-result")
async def security_result(
    run_id: str,
    data: SecurityResultRequest,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(verify_internal),
):
    """Called by Security Scanner after a scan completes."""
    run = await db.get(TestRun, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")

    existing = run.metadata or {}
    run.metadata = {
        **existing,
        "security": {
            "score": data.score,
            "grade": data.grade,
            "total_checks": data.total_checks,
            "duration_seconds": data.duration_seconds,
            "findings_count": len(data.findings),
            "summary": data.summary,
            "findings": data.findings[:50],  # cap stored findings
        },
    }
    await db.flush()
    return {"message": "Security result stored", "score": data.score, "grade": data.grade}


@router.post("/runs/{run_id}/healing-result")
async def healing_result(
    run_id: str,
    data: HealingResultRequest,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(verify_internal),
):
    """Called by Healing service after auto-healing completes."""
    run = await db.get(TestRun, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")

    existing = run.metadata or {}
    run.metadata = {
        **existing,
        "healing": {
            "auto_healed": data.auto_healed,
            "needs_human": data.needs_human,
            "healing_rate": data.healing_rate,
        },
    }
    await db.flush()
    return {"message": "Healing result stored"}


@router.post("/runs/{run_id}/visual-result")
async def visual_result(
    run_id: str,
    data: VisualResultRequest,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(verify_internal),
):
    """Called by Visual service after screenshot comparison."""
    run = await db.get(TestRun, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")

    existing = run.metadata or {}
    run.metadata = {
        **existing,
        "visual": {
            "total_pages": data.total_pages,
            "regressions": data.regressions,
            "results": data.results,
        },
    }
    await db.flush()
    return {"message": "Visual result stored"}
    status: str
    passed_tests: int
    failed_tests: int
    skipped_tests: int
    total_tests: int
    duration_seconds: float
    error_message: Optional[str] = None
    test_cases: List[dict] = []


@router.patch("/runs/{run_id}/status")
async def update_run_status(
    run_id: str,
    data: StatusUpdateRequest,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(verify_internal),
):
    """Called by Crawler and Executor to update run status."""
    try:
        status = TestRunStatus(data.status)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid status: {data.status}")

    import asyncio

    run = None

    for _ in range(10):
        try:
            svc = ProjectService(db)
            run = await svc.update_run_status(
                run_id=run_id,
                status=status,
                error_message=data.error_message,
                error_stage=data.error_stage,
                ai_summary=data.ai_summary,
            )

            if run:
                break

        except Exception:
            await asyncio.sleep(1)

    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    return {"run_id": run_id, "status": run.status}


@router.patch("/runs/{run_id}/plan")
async def update_run_plan(
    run_id: str,
    data: PlanUpdateRequest,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(verify_internal),
):
    """Called by AI Orchestrator to store the generated test plan."""
    run = await db.get(TestRun, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")

    run.ai_test_plan = data.ai_test_plan
    if data.crawl_summary:
        run.metadata = {**(run.metadata or {}), "crawl_summary": data.crawl_summary}
    await db.flush()
    return {"message": "Plan stored"}


@router.post("/runs/{run_id}/complete")
async def complete_run(
    run_id: str,
    data: CompleteRequest,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(verify_internal),
):
    """Called by Executor when all tests have finished."""
    run = await db.get(TestRun, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")

    # Update run stats
    run.status = TestRunStatus(data.status)
    run.passed_tests = data.passed_tests
    run.failed_tests = data.failed_tests
    run.skipped_tests = data.skipped_tests
    run.total_tests = data.total_tests
    run.duration_seconds = data.duration_seconds
    run.error_message = data.error_message

    if not run.started_at:
        run.started_at = datetime.now(timezone.utc)

    run.completed_at = datetime.now(timezone.utc)
    # Save individual test cases
    for case_data in data.test_cases:
        case = TestCase(
            test_run_id=run_id,
            project_id=run.project_id,
            org_id=run.org_id,
            name=case_data.get("name", "Unknown"),
            file_path=case_data.get("file_path"),
            status=case_data.get("status", "failed"),
            duration_ms=case_data.get("duration_ms"),
            error_message=case_data.get("error_message"),
            stack_trace=case_data.get("stack_trace"),
            retry_count=case_data.get("retry_count", 0),
            screenshot_url=case_data.get("screenshot_url"),
            video_url=case_data.get("video_url"),
        )
        db.add(case)

    await db.flush()

    # Update project stats
    svc = ProjectService(db)
    await svc._update_project_stats(run.project_id)

    # ── Fire test.completed / test.failed event ───────────────
    try:
        import httpx, os
        events_url = os.getenv("EVENTS_SERVICE_URL", "http://events:8017")
        payload = {}

        pass_rate = round(data.passed_tests / data.total_tests * 100, 1) if data.total_tests else 0

        event_name = "test.completed" if data.status == "passed" else "test.failed"
        async with httpx.AsyncClient(timeout=2.0) as client:
            print("RUN TEST METADATA:", run.test_metadata)
            print("EMAIL BEING SENT:", run.test_metadata.get("email"))
            await client.post(f"{events_url}/api/v1/events/publish", json={
                "event": event_name,
                "org_id": run.org_id,
                "project_id": run.project_id,
                "actor_id": str(run.created_by_id) if run.created_by_id else None,
                "source_service": "projects",
                "payload": {
                    "run_id": run_id,
                    "email": run.test_metadata.get("email"),
                    "status": data.status,
                    "passed": data.passed_tests,
                    "failed": data.failed_tests,
                    "total": data.total_tests,
                    "pass_rate": pass_rate,
                    "duration_seconds": data.duration_seconds,
                    "trigger_type": run.trigger_type,
                    "git_branch": run.git_branch,
                },
            })
    except Exception:
        pass

    # Notify GitHub if applicable
    if run.git_commit_sha:
        from sqlalchemy import select
        from app.models.project import GitHubIntegration
        integration = await db.scalar(
            select(GitHubIntegration).where(GitHubIntegration.project_id == run.project_id)
        )
        if integration:
            from app.services.github_service import GitHubWebhookService
            gh_svc = GitHubWebhookService(db)
            await gh_svc.post_run_result(run, integration)

    return {"message": "Run completed", "status": data.status
}
