"""Tests for the Reports Service."""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from httpx import AsyncClient, ASGITransport


@pytest.fixture
def app():
    from app.main import app as _app
    return _app


@pytest.mark.asyncio
async def test_list_report_types(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/v1/reports/types")
        assert resp.status_code == 200
        types = resp.json()
        assert isinstance(types, list)
        assert len(types) >= 8
        ids = [t["id"] for t in types]
        assert "executive_summary" in ids
        assert "test_reliability" in ids
        assert "compliance_evidence" in ids


@pytest.mark.asyncio
async def test_generate_csv_report(app):
    with patch("httpx.AsyncClient") as mock_cls:
        inst = AsyncMock()
        inst.__aenter__ = AsyncMock(return_value=inst)
        inst.__aexit__ = AsyncMock(return_value=None)
        inst.get.return_value.status_code = 200
        inst.get.return_value.json = MagicMock(return_value={
            "reliability": {"total_runs": 50, "pass_rate": 94.0, "failed_runs": 3, "period_days": 30},
            "deployments": {"total_deployments": 10, "rollbacks": 1, "rollback_rate": 10.0},
            "healing": {"auto_healed_tests": 5},
        })
        mock_cls.return_value = inst

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post("/api/v1/reports/generate", json={
                "org_id": "org-1",
                "report_type": "test_reliability",
                "format": "csv",
                "days": 30,
            })
            assert resp.status_code == 200
            assert "text/csv" in resp.headers["content-type"]
            assert b"Pass Rate" in resp.content or b"pass_rate" in resp.content.lower()


@pytest.mark.asyncio
async def test_generate_json_report(app):
    with patch("httpx.AsyncClient") as mock_cls:
        inst = AsyncMock()
        inst.__aenter__ = AsyncMock(return_value=inst)
        inst.__aexit__ = AsyncMock(return_value=None)
        inst.get.return_value.status_code = 200
        inst.get.return_value.json = MagicMock(return_value={
            "reliability": {"total_runs": 50, "pass_rate": 94.0, "failed_runs": 3, "period_days": 30},
            "deployments": {}, "healing": {},
        })
        mock_cls.return_value = inst

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post("/api/v1/reports/generate", json={
                "org_id": "org-1",
                "report_type": "executive_summary",
                "format": "json",
                "days": 30,
            })
            assert resp.status_code == 200
            data = resp.json()
            assert data["report_type"] == "executive_summary"
            assert "generated_at" in data
            assert "data" in data


@pytest.mark.asyncio
async def test_unknown_report_type_returns_400(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post("/api/v1/reports/generate", json={
            "org_id": "org-1",
            "report_type": "nonexistent_type_xyz",
            "format": "csv",
            "days": 30,
        })
        assert resp.status_code == 400


@pytest.mark.asyncio
async def test_health(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/health")
        assert resp.status_code == 200
