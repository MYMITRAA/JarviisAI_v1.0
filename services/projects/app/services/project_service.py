"""
ProjectService — CRUD and test run orchestration.
This service coordinates: Projects → Crawl → Generate → Execute → Results
"""

from datetime import datetime, timezone, timedelta
from typing import Optional, List, Tuple
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, update, desc, text
from fastapi import HTTPException, status
import httpx
import logging

from app.models.project import (
    Project, ProjectEnvironment, GitHubIntegration,
    TestRun, TestCase, ProjectType, TestRunStatus, TriggerType
)
from app.schemas.project import (
    ProjectCreate, ProjectUpdate, TestRunCreate,
    GitHubIntegrationCreate
)
from app.core.config import settings
# Service URLs come from settings (config.py)
_USAGE_URL = settings.USAGE_SERVICE_URL if hasattr(settings, "USAGE_SERVICE_URL") else "http://usage:8018"
_EVENTS_URL = settings.EVENTS_SERVICE_URL if hasattr(settings, "EVENTS_SERVICE_URL") else "http://events:8017"

logger = logging.getLogger("jarviis.projects.service")


class ProjectService:
    def __init__(self, db: AsyncSession):
        self.db = db

    # ── Projects ──────────────────────────────────────────────

    async def create(self, data: ProjectCreate, org_id: str, user_id: str) -> Project:
        # Check slug uniqueness within org
        existing = await self.db.scalar(
            select(Project).where(Project.org_id == org_id, Project.slug == data.slug)
        )
        if existing:
            raise HTTPException(status_code=409, detail="A project with this slug already exists")

        project = Project(
            org_id=org_id,
            created_by_id=user_id,
            name=data.name,
            slug=data.slug,
            description=data.description,
            project_type=data.project_type,
            project_url=data.project_url,
            test_config=data.test_config or {},
        )
        self.db.add(project)
        await self.db.flush()

        # Create default environment
        env = ProjectEnvironment(
            project_id=project.id,
            org_id=org_id,
            name="default",
            base_url=data.project_url,
            is_default=True,
        )
        self.db.add(env)
        await self.db.flush()

        logger.info(f"Project created: {project.slug} in org {org_id}")
        return project

    async def get(self, project_id: str, org_id: str) -> Optional[Project]:
        return await self.db.scalar(
            select(Project).where(Project.id == project_id, Project.org_id == org_id, Project.is_active == True)
        )

    async def get_by_slug(self, slug: str, org_id: str) -> Optional[Project]:
        return await self.db.scalar(
            select(Project).where(Project.slug == slug, Project.org_id == org_id, Project.is_active == True)
        )

    async def list(
        self, org_id: str, page: int = 1, page_size: int = 20,
        project_type: Optional[str] = None,
    ) -> Tuple[List[Project], int]:
        q = select(Project).where(Project.org_id == org_id, Project.is_active == True)
        if project_type:
            q = q.where(Project.project_type == project_type)

        total = await self.db.scalar(select(func.count()).select_from(q.subquery()))
        projects = (await self.db.execute(
            q.order_by(desc(Project.last_run_at), desc(Project.created_at))
             .offset((page - 1) * page_size).limit(page_size)
        )).scalars().all()

        return list(projects), total or 0

    async def update(self, project_id: str, org_id: str, data: ProjectUpdate) -> Project:
        project = await self.get(project_id, org_id)
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")

        if data.name is not None: project.name = data.name
        if data.description is not None: project.description = data.description
        if data.project_url is not None: project.project_url = data.project_url
        if data.test_config is not None: project.test_config = data.test_config

        await self.db.flush()
        return project

    async def delete(self, project_id: str, org_id: str) -> None:
        project = await self.get(project_id, org_id)
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")
        project.is_active = False
        await self.db.flush()

    async def get_stats(self, org_id: str) -> dict:
        """Dashboard stats for an organization."""
        today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0)

        total_projects = await self.db.scalar(
            select(func.count(Project.id)).where(Project.org_id == org_id, Project.is_active == True)
        ) or 0

        runs_today = await self.db.execute(
            select(
                func.count(TestRun.id).label("total"),
                func.sum(TestRun.passed_tests).label("passed"),
                func.sum(TestRun.total_tests).label("tests"),
                func.count(TestRun.id).filter(TestRun.status == TestRunStatus.FAILED).label("failed"),
            ).where(
                TestRun.org_id == org_id,
                TestRun.created_at >= today
            )
        )
        row = runs_today.first()

        active_runs = await self.db.scalar(
            select(func.count(TestRun.id)).where(
                TestRun.org_id == org_id,
                TestRun.status.in_([TestRunStatus.RUNNING, TestRunStatus.CRAWLING, TestRunStatus.GENERATING, TestRunStatus.QUEUED])
            )
        ) or 0

        pass_rate = None
        if row and row.tests and row.tests > 0:
            pass_rate = round((row.passed or 0) / row.tests * 100, 1)

        return {
            "total_projects": total_projects,
            "total_runs_today": (row.total or 0) if row else 0,
            "pass_rate_today": pass_rate or 0.0,
            "failed_runs_today": (row.failed or 0) if row else 0,
            "active_runs": active_runs or 0,
            "tests_run_today": (row.tests or 0) if row else 0,
        }

    # ── GitHub Integration ────────────────────────────────────

    async def connect_github(
        self, project_id: str, org_id: str, data: GitHubIntegrationCreate
    ) -> GitHubIntegration:
        project = await self.get(project_id, org_id)
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")

        owner, repo = data.repo_full_name.split("/")

        # Remove old integration if exists
        existing = await self.db.scalar(
            select(GitHubIntegration).where(GitHubIntegration.project_id == project_id)
        )
        if existing:
            await self.db.delete(existing)
            await self.db.flush()

        integration = GitHubIntegration(
            project_id=project_id,
            org_id=org_id,
            installation_id=data.installation_id,
            repo_owner=owner,
            repo_name=repo,
            repo_full_name=data.repo_full_name,
            default_branch=data.default_branch,
            trigger_on_push=data.trigger_on_push,
            trigger_on_pr=data.trigger_on_pr,
            branch_filter=data.branch_filter,
        )
        self.db.add(integration)
        await self.db.flush()
        return integration

    async def get_integration_by_repo(self, repo_full_name: str) -> Optional[GitHubIntegration]:
        return await self.db.scalar(
            select(GitHubIntegration).where(
                GitHubIntegration.repo_full_name == repo_full_name,
                GitHubIntegration.is_active == True,
            )
        )

    # ── Test Runs ─────────────────────────────────────────────

    async def create_run(
        self, project_id: str, org_id: str, user_id: str, data: TestRunCreate
    ) -> TestRun:

        project = await self.get(project_id, org_id)

        user_email = None

        try:
            result = await self.db.execute(
                text("""
                    SELECT settings->>'notification_email' AS email
                    FROM organizations
                    WHERE id = :oid
                    LIMIT 1
                """),
                {"oid": str(org_id)}
            )

            row = result.first()
            print("ORG QUERY ROW:", row)

            if row:
                user_email = row[0]
            print("FETCHED EMAIL:", user_email)#line

        except Exception as e:
            print("EMAIL FETCH ERROR:", str(e))
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")

        if not project.project_url and not data.test_metadata.get("apk_url"):
            raise HTTPException(
                status_code=400,
                detail="Project has no URL configured. Set a project URL before running tests.",
            )

        # ── Usage enforcement ─────────────────────────────────
        # Fetch effective plan (respects 2-day trial overlay)
        plan = "starter"
        try:
            plan_row = await self.db.execute(
                text("SELECT plan, trial_ends_at FROM organizations WHERE id = :oid"),
                {"oid": org_id}
            )
            plan_data = plan_row.first()
            if plan_data:
                raw_plan = str(plan_data.plan).lower()
                trial_ends = plan_data.trial_ends_at
                # Apply trial overlay: if trial active, treat as pro
                if trial_ends and hasattr(trial_ends, 'replace'):
                    trial_dt = trial_ends if trial_ends.tzinfo else trial_ends.replace(tzinfo=timezone.utc)
                    if trial_dt > datetime.now(timezone.utc):
                        plan = "pro"
                    else:
                        plan = raw_plan
                else:
                    plan = raw_plan
        except Exception as e:
            logger.warning(f"Could not fetch org plan, defaulting to starter: {e}")

        try:
            usage_url = _USAGE_URL
            async with httpx.AsyncClient(timeout=3.0) as client:
                resp = await client.post(f"{usage_url}/api/v1/usage/check", json={
                    "org_id": org_id,
                    "plan": plan,
                    "metric": "test_runs",
                    "increment_by": 1,
                })
                if resp.status_code == 200:
                    result = resp.json()
                    if not result.get("allowed", True):
                        raise HTTPException(
                            status_code=429,
                            detail={
                                "error": "plan_limit_reached",
                                "message": result.get("error", "Monthly test run limit reached"),
                                "current": result.get("current"),
                                "limit": result.get("limit"),
                                "upgrade_url": "/settings/billing",
                            }
                        )
        except HTTPException:
            raise
        except Exception as e:
            print(f"Usage check skipped (dev mode): {e}")
        print("FINAL USER EMAIL:", user_email)
        print("FINAL TEST METADATA:", {
            **(data.test_metadata or {}),
            "email": (
                data.test_metadata.get("email")
                if data.test_metadata and data.test_metadata.get("email")
                else user_email
            )
        })

        run = TestRun(
            project_id=project_id,
            org_id=org_id,
            created_by_id=user_id,
            status=TestRunStatus.PENDING,
            trigger_type=data.trigger_type,
            git_branch=data.git_branch,
            git_commit_sha=data.git_commit_sha,
            git_pr_number=data.git_pr_number,
            environment_name=data.environment_name,
            browsers=data.browsers,
            test_metadata={
                **(data.test_metadata or {}),
                "email": (
                    data.test_metadata.get("email")
                    if data.test_metadata and data.test_metadata.get("email")
                    else user_email
                )
            },     
        )
        self.db.add(run)
        await self.db.commit()
        await self.db.refresh(run)
        print("FINAL TEST METADATA FROM DB:", run.test_metadata)
        # ── Publish event ─────────────────────────────────────
        try:
            events_url = _EVENTS_URL
            async with httpx.AsyncClient(timeout=2.0) as client:
                await client.post(f"{events_url}/api/v1/events/publish", json={
                    "event": "test.started",
                    "org_id": org_id,
                    "project_id": project_id,
                    "actor_id": user_id,
                    "source_service": "projects",
                    "payload": {"run_id": str(run.id), "trigger_type": data.trigger_type, "plan": plan},
                })
        except Exception:
            pass


        logger.info(f"Test run created: {run.id} for project {project_id}")
        return run

    async def get_run(self, run_id: str, org_id: str) -> Optional[TestRun]:
        return await self.db.scalar(
            select(TestRun).where(TestRun.id == run_id, TestRun.org_id == org_id)
        )

    async def list_runs(
        self, project_id: str, org_id: str, page: int = 1, page_size: int = 20,
        status_filter: Optional[str] = None,
    ) -> Tuple[List[TestRun], int]:
        q = select(TestRun).where(TestRun.project_id == project_id, TestRun.org_id == org_id)
        if status_filter:
            q = q.where(TestRun.status == status_filter)

        total = await self.db.scalar(select(func.count()).select_from(q.subquery()))
        runs = (await self.db.execute(
            q.order_by(desc(TestRun.created_at))
             .offset((page - 1) * page_size).limit(page_size)
        )).scalars().all()

        return list(runs), total or 0

    async def update_run_status(
        self, run_id: str, status: TestRunStatus,
        error_message: Optional[str] = None,
        error_stage: Optional[str] = None,
        ai_summary: Optional[str] = None,
    ) -> TestRun:
        run = await self.db.get(TestRun, run_id)
        if not run:
            raise HTTPException(status_code=404, detail="Test run not found")

        run.status = status
        print("STATUS COMMITTED:", run.id, run.status)
        if error_message:
            run.error_message = error_message
        if error_stage:
            run.error_stage = error_stage
        if ai_summary:
            run.ai_summary = ai_summary

        if status == TestRunStatus.RUNNING and not run.started_at:
            run.started_at = datetime.now(timezone.utc)
        if status in [TestRunStatus.PASSED, TestRunStatus.FAILED, TestRunStatus.ERROR, TestRunStatus.CANCELLED]:
            run.completed_at = datetime.now(timezone.utc)
            if run.started_at:
                run.duration_seconds = (run.completed_at - run.started_at).total_seconds()

        await self.db.commit()
        await self.db.refresh(run)

        # Update project stats
        await self._update_project_stats(run.project_id)

        return run

    async def get_run_cases(self, run_id: str, org_id: str) -> List[TestCase]:
        result = await self.db.execute(
            select(TestCase).where(
                TestCase.test_run_id == run_id,
                TestCase.org_id == org_id,
            ).order_by(TestCase.status, TestCase.name)
        )
        return list(result.scalars().all())

    async def _update_project_stats(self, project_id: str) -> None:
        """Update denormalized stats on project after each run."""
        last_run = await self.db.scalar(
            select(TestRun)
            .where(TestRun.project_id == project_id)
            .order_by(desc(TestRun.created_at))
            .limit(1)
        )
        if not last_run:
            return

        total_runs = await self.db.scalar(
            select(func.count(TestRun.id)).where(TestRun.project_id == project_id)
        ) or 0

        # Calculate 30-day pass rate
        thirty_days_ago = datetime.now(timezone.utc) - timedelta(days=30)
        recent = await self.db.execute(
            select(
                func.sum(TestRun.passed_tests).label("passed"),
                func.sum(TestRun.total_tests).label("total"),
            ).where(
                TestRun.project_id == project_id,
                TestRun.created_at >= thirty_days_ago,
                TestRun.total_tests > 0,
            )
        )
        row = recent.first()
        pass_rate = None
        if row and row.total and row.total > 0:
            pass_rate = round((row.passed or 0) / row.total * 100, 1)

        await self.db.execute(
            update(Project)
            .where(Project.id == project_id)
            .values(
                last_run_at=last_run.created_at,
                last_run_status=last_run.status,
                total_runs=total_runs,
                pass_rate=pass_rate,
            )
        )
        await self.db.commit()

    # ── Run orchestration ─────────────────────────────────────

    async def trigger_run_pipeline(self, run_id: str) -> None:
        """
        Kick off the full test pipeline asynchronously.
        Pipeline: PENDING → QUEUED → CRAWLING → GENERATING → RUNNING → PASSED/FAILED

        In production this fires off to a Kafka topic / task queue.
        For Phase 1, we call the crawler service directly via HTTP.
        """
        run = await self.db.get(TestRun, run_id)
        if not run:
            return

        project = await self.db.get(Project, run.project_id)
        if not project:
            return

        # Fire and forget to crawler
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                await client.post(
                    f"{settings.CRAWLER_SERVICE_URL}/api/v1/crawl/start",
                    json={
                        "run_id": run_id,
                        "project_id": run.project_id,
                        "org_id": run.org_id,
                        "url": project.project_url,
                        "project_type": project.project_type,
                        "test_config": project.test_config or {},
                        "browsers": run.browsers or ["chromium"],
                    },
                )
            run.status = TestRunStatus.QUEUED
            run.queued_at = datetime.now(timezone.utc)
            await self.db.flush()
        except Exception as e:
            logger.error(f"Failed to trigger crawl for run {run_id}: {e}")
            run.status = TestRunStatus.ERROR
            run.error_message = f"Failed to start crawler: {str(e)}"
            run.error_stage = "trigger"
            await self.db.flush()
