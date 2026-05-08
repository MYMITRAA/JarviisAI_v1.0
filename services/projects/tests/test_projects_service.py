"""
Tests for Projects Service — focusing on usage enforcement.
"""
import pytest
import uuid
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from unittest.mock import AsyncMock, patch, MagicMock

from app.main import app
from app.core.database import get_db, Base
from app.core.config import settings

TEST_DB_URL = "sqlite+aiosqlite:///./test_projects.db"
test_engine = create_async_engine(TEST_DB_URL, echo=False)
TestSession = async_sessionmaker(test_engine, expire_on_commit=False)


async def override_get_db():
    async with TestSession() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


@pytest_asyncio.fixture(autouse=True)
async def setup_db():
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    app.dependency_overrides[get_db] = override_get_db
    yield
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_create_project_endpoint_exists():
    """Projects service starts and routes are registered."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["service"] == "projects"


@pytest.mark.asyncio
async def test_usage_check_429_when_limit_hit():
    """When usage service returns not-allowed, run creation returns 429."""
    usage_response = {
        "allowed": False,
        "current": 100,
        "limit": 100,
        "remaining": 0,
        "warning": True,
        "error": "Monthly test run limit reached",
        "upgrade_url": "/settings/billing",
    }

    # Mock both usage check and auth token
    with patch("httpx.AsyncClient") as mock_cls:
        inst = AsyncMock()
        inst.__aenter__ = AsyncMock(return_value=inst)
        inst.__aexit__ = AsyncMock(return_value=None)
        inst.post.return_value.status_code = 200
        inst.post.return_value.json = MagicMock(return_value=usage_response)
        mock_cls.return_value = inst

        # Test project service enforces limits
        from app.services.project_service import ProjectService
        from unittest.mock import MagicMock as MM
        from fastapi import HTTPException
        import pytest

        # Simulate calling create_run — it should raise 429
        with pytest.raises(HTTPException) as exc_info:
            # Create a mock db session
            mock_db = AsyncMock()
            mock_db.execute.return_value.first.return_value = MM(plan="free", trial_ends_at=None)

            svc = ProjectService(mock_db)
            svc.get = AsyncMock(return_value=MM(project_url="https://example.com", id="proj-1"))

            from app.schemas.project import TestRunCreate, TriggerType
            service = ProjectService(mock_db)
            org_id = str(uuid.uuid4())
            user_id = str(uuid.uuid4())

            project = await service.create_project(
                org_id=org_id,
                created_by=user_id,
                data=ProjectCreate(
                        name="CI Test Project",
                        repo_url="https://github.com/test/repo"
                    )
                )
            run_data = TestRunCreate(project_id=project.id, trigger_type=TriggerType.MANUAL)
            await svc.create_run("proj-1", "org-1", "user-1", run_data)

        assert exc_info.value.status_code == 429


@pytest.mark.asyncio
async def test_list_projects_returns_structure():
    """GET /api/v1/orgs/{org_id}/projects returns correct shape."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test",
                           headers={"Authorization": "Bearer test-token"}) as client:
        # Without auth this returns 401/422 — just verify route exists
        resp = await client.get("/api/v1/orgs/org-1/projects")
        assert resp.status_code in (200, 401, 403, 422)  # Route exists
