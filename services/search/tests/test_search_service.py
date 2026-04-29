"""Tests for the Search Service."""
import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, patch, MagicMock
from httpx import AsyncClient, ASGITransport


@pytest.fixture
def app():
    from app.main import app as _app
    return _app


@pytest.mark.asyncio
async def test_search_requires_min_2_chars(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/v1/search?q=a&org_id=org-1")
        assert resp.status_code == 422  # Validation error


@pytest.mark.asyncio
async def test_search_returns_results_structure(app):
    """Mock downstream services and verify result structure."""
    mock_projects_response = {
        "projects": [
            {"id": "proj-1", "name": "checkout-flow", "project_url": "https://example.com",
             "last_run_status": "passed", "created_at": "2026-01-01T00:00:00Z"}
        ]
    }

    with patch("httpx.AsyncClient") as mock_cls:
        mock_inst = AsyncMock()
        mock_inst.__aenter__ = AsyncMock(return_value=mock_inst)
        mock_inst.__aexit__ = AsyncMock(return_value=None)
        mock_inst.get = AsyncMock()
        mock_inst.get.return_value.status_code = 200
        mock_inst.get.return_value.json = MagicMock(return_value=mock_projects_response)
        mock_cls.return_value = mock_inst

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/api/v1/search?q=checkout&org_id=org-1")
            assert resp.status_code == 200
            data = resp.json()
            assert "query" in data
            assert "results" in data
            assert "total" in data
            assert data["query"] == "checkout"


@pytest.mark.asyncio
async def test_search_with_status_filter(app):
    with patch("httpx.AsyncClient") as mock_cls:
        mock_inst = AsyncMock()
        mock_inst.__aenter__ = AsyncMock(return_value=mock_inst)
        mock_inst.__aexit__ = AsyncMock(return_value=None)
        mock_inst.get.return_value.status_code = 200
        mock_inst.get.return_value.json = MagicMock(return_value={"projects": []})
        mock_cls.return_value = mock_inst

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/api/v1/search?q=test&org_id=org-1&status=failed")
            assert resp.status_code == 200


@pytest.mark.asyncio
async def test_health(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["service"] == "search"
