"""Tests for the Audit Service."""
import pytest
import pytest_asyncio
import json
from unittest.mock import AsyncMock
from datetime import datetime, timezone


@pytest_asyncio.fixture
async def mock_redis():
    zsets = {}

    class MockRedis:
        async def zadd(self, key, mapping):
            zsets.setdefault(key, {}); zsets[key].update(mapping); return len(mapping)
        async def zremrangebyrank(self, key, start, end): return 0
        async def expire(self, key, seconds): return True
        async def zrangebyscore(self, key, min_score, max_score, withscores=False, offset=0, count=None):
            items = zsets.get(key, {})
            # Return all items (ignore score filter in tests)
            return list(items.keys())[:count or 1000]
        async def ping(self): return True
        async def aclose(self): pass

    return MockRedis()


@pytest_asyncio.fixture
async def redis_set(mock_redis):
    """Expose the zsets dict for assertions."""
    zsets = {}
    mock_redis._zsets = zsets
    return mock_redis, zsets


@pytest.mark.asyncio
async def test_store_audit_entry():
    from httpx import AsyncClient, ASGITransport
    from unittest.mock import AsyncMock, patch
    import app.main as main_module
    from app.main import app

    zsets = {}

    class MockRedis:
        async def zadd(self, key, mapping):
            zsets.setdefault(key, {}); zsets[key].update(mapping); return 1
        async def zremrangebyrank(self, key, *a): return 0
        async def expire(self, key, seconds): return True
        async def zrangebyscore(self, key, *a, **kw):
            return list(zsets.get(key, {}).keys())
        async def ping(self): return True
        async def aclose(self): pass

    main_module._redis = MockRedis()
    # Patch event consumer to not start background task


    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post("/api/v1/audit/write", json={
            "event": "deploy.started",
            "org_id": "org-test",
            "actor_id": "user-123",
            "source": "deploy",
            "payload": {"image_tag": "v1.2.3"},
        })
        assert resp.status_code == 200
        assert resp.json()["written"] is True


@pytest.mark.asyncio
async def test_export_returns_json():
    from httpx import AsyncClient, ASGITransport
    from app.main import app
    import app.main as main_module

    zsets = {"audit:org-export": {
        json.dumps({"id": "1", "event": "test.completed", "org_id": "org-export",
                    "timestamp": datetime.now(timezone.utc).isoformat()}): 1000.0
    }}

    class MockRedis:
        async def zadd(self, key, mapping): zsets.setdefault(key, {}).update(mapping); return 1
        async def zremrangebyrank(self, *a): return 0
        async def expire(self, *a): return True
        async def zrangebyscore(self, key, *a, **kw):
            return list(zsets.get(key, {}).keys())
        async def ping(self): return True
        async def aclose(self): pass

    main_module._redis = MockRedis()
    # Patch event consumer to not start background task


    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/v1/audit/org-export/export?days=30")
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("application/json")


@pytest.mark.asyncio
async def test_health():
    from httpx import AsyncClient, ASGITransport
    from app.main import app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/health")
        assert resp.status_code == 200
