"""Tests for Feature Flags Service."""
import pytest
import pytest_asyncio
import json
from unittest.mock import AsyncMock
from httpx import AsyncClient, ASGITransport


@pytest.fixture
def app():
    import sys
    import os
    from unittest.mock import AsyncMock, MagicMock
    sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
    
    # Patch Redis before importing app so lifespan doesn't connect
    store = {}
    mock_redis = AsyncMock()
    mock_redis.get = AsyncMock(side_effect=lambda k: store.get(k))
    mock_redis.set = AsyncMock(side_effect=lambda k, v, **kw: store.update({k: v}))
    mock_redis.delete = AsyncMock(return_value=True)
    mock_redis.ping = AsyncMock(return_value=True)
    mock_redis.aclose = AsyncMock()
    
    import app.main as main_module
    main_module._redis = mock_redis
    
    from app.main import app as _app
    return _app


@pytest.mark.asyncio
async def test_evaluate_known_flag_enabled(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post("/api/v1/flags/api_testing/evaluate",
                                 json={"org_id": "org-1", "plan": "pro"})
        assert resp.status_code == 200
        data = resp.json()
        assert "enabled" in data
        assert "reason" in data


@pytest.mark.asyncio
async def test_evaluate_unknown_flag_returns_false(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post("/api/v1/flags/nonexistent_flag_xyz/evaluate",
                                 json={"org_id": "org-1", "plan": "pro"})
        assert resp.status_code == 200
        assert resp.json()["enabled"] is False


@pytest.mark.asyncio
async def test_plan_gating_enterprise_feature_blocked_on_starter(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post("/api/v1/flags/enterprise_sso/evaluate",
                                 json={"org_id": "org-1", "plan": "starter"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["enabled"] is False
        assert "plan" in data.get("reason", "").lower()


@pytest.mark.asyncio
async def test_plan_gating_enterprise_feature_allowed_on_enterprise(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post("/api/v1/flags/enterprise_sso/evaluate",
                                 json={"org_id": "org-1", "plan": "enterprise"})
        assert resp.status_code == 200
        assert resp.json()["enabled"] is True


@pytest.mark.asyncio
async def test_evaluate_all_flags_returns_dict(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/v1/flags/evaluate-all?org_id=org-1&plan=pro")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, dict)
        assert len(data) > 0
        assert all(isinstance(v, bool) for v in data.values())


@pytest.mark.asyncio
async def test_admin_set_flag_requires_secret(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Without secret
        resp = await client.post("/api/v1/flags/test_flag",
                                 json={"enabled": True, "rollout_pct": 100, "plans": []})
        assert resp.status_code == 403

        # With correct secret
        resp2 = await client.post("/api/v1/flags/test_flag",
                                  json={"enabled": True, "rollout_pct": 100, "plans": []},
                                  headers={"X-Internal-Secret": "jarviis-internal-secret"})
        assert resp2.status_code == 200


@pytest.mark.asyncio
async def test_health_endpoint(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["service"] == "feature-flags"
