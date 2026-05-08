"""Tests for the Compliance Service."""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from httpx import AsyncClient, ASGITransport


@pytest.fixture
def app():
    from app.main import app as _app
    return _app


@pytest.mark.asyncio
async def test_soc2_pack_returns_zip(app):
    mock_audit = {"entries": [
        {"id": "1", "event": "deploy.started", "org_id": "org-1",
         "actor_id": "user-1", "timestamp": "2026-01-01T00:00:00Z", "payload": {}}
    ]}
    with patch("httpx.AsyncClient") as mock_cls:
        inst = AsyncMock()
        inst.__aenter__ = AsyncMock(return_value=inst)
        inst.__aexit__ = AsyncMock(return_value=None)
        inst.get.return_value.status_code = 200
        inst.get.return_value.json = MagicMock(return_value=mock_audit)
        mock_cls.return_value = inst

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/api/v1/compliance/org-1/soc2-pack?days=30")
            assert resp.status_code == 200
            assert "application/zip" in resp.headers["content-type"]
            # Verify ZIP content
            import zipfile, io
            zf = zipfile.ZipFile(io.BytesIO(resp.content))
            names = zf.namelist()
            assert "README.txt" in names
            assert "audit_log.json" in names
            assert "access_control.json" in names


@pytest.mark.asyncio
async def test_gdpr_export_returns_json(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post("/api/v1/compliance/org-1/gdpr/export?user_id=user-123")
        assert resp.status_code == 200
        assert "application/json" in resp.headers["content-type"]
        import json
        data = json.loads(resp.content)
        assert data["user_id"] == "user-123"
        assert "exported_at" in data


@pytest.mark.asyncio
async def test_gdpr_delete_returns_confirmation(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.delete("/api/v1/compliance/org-1/gdpr/delete/user-456")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "deletion_processed"
        assert "confirmation_id" in data


@pytest.mark.asyncio
async def test_health(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["service"] == "compliance"
