"""Tests for the Analytics Service."""
import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, patch, MagicMock
from httpx import AsyncClient, ASGITransport


@pytest.fixture
def app():
    from app.main import app as _app
    return _app


@pytest.mark.asyncio
async def test_overview_returns_correct_structure(app):
    mock_data = {
        "runs": [
            {"status": "passed", "passed_tests": 80, "failed_tests": 2, "total_tests": 82},
            {"status": "failed", "passed_tests": 40, "failed_tests": 10, "total_tests": 50},
        ]
    }
    with patch("httpx.AsyncClient") as mock_cls:
        inst = AsyncMock()
        inst.__aenter__ = AsyncMock(return_value=inst)
        inst.__aexit__ = AsyncMock(return_value=None)
        inst.get.return_value.status_code = 200
        inst.get.return_value.json = MagicMock(return_value=mock_data)
        mock_cls.return_value = inst

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/api/v1/analytics/org-1/overview?days=30")
            assert resp.status_code == 200
            data = resp.json()
            assert "reliability" in data
            assert "deployments" in data
            assert "healing" in data
            assert "period_days" in data
            assert data["period_days"] == 30


@pytest.mark.asyncio
async def test_reliability_pass_rate_calculated(app):
    mock_data = {
        "runs": [
            {"status": "passed"}, {"status": "passed"},
            {"status": "failed"}, {"status": "passed"},
        ]
    }
    with patch("httpx.AsyncClient") as mock_cls:
        inst = AsyncMock()
        inst.__aenter__ = AsyncMock(return_value=inst)
        inst.__aexit__ = AsyncMock(return_value=None)
        inst.get.return_value.status_code = 200
        inst.get.return_value.json = MagicMock(return_value=mock_data)
        mock_cls.return_value = inst

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/api/v1/analytics/org-1/reliability?days=30")
            assert resp.status_code == 200
            data = resp.json()
            assert data["total_runs"] == 4
            assert data["pass_rate"] == 75.0


@pytest.mark.asyncio
async def test_healing_roi_returns_structure(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/v1/analytics/org-1/healing-roi?days=30")
        assert resp.status_code == 200
        data = resp.json()
        assert "auto_healed_tests" in data
        assert "healing_rate_pct" in data
        assert "estimated_hours_saved" in data


@pytest.mark.asyncio
async def test_period_validation(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Too small
        resp = await client.get("/api/v1/analytics/org-1/overview?days=1")
        assert resp.status_code == 422
        # Too large
        resp2 = await client.get("/api/v1/analytics/org-1/overview?days=400")
        assert resp2.status_code == 422


@pytest.mark.asyncio
async def test_health(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/health")
        assert resp.status_code == 200
