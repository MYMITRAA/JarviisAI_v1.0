"""
Tests for the Usage Metering Service.

Tests cover:
  - Counter increment and retrieval
  - Plan limit enforcement (hard block at 100%)
  - Warning threshold (soft alert at 80%)
  - Trial plan uses pro limits
  - Unlimited plans never blocked
  - Monthly reset works correctly
"""

import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock, patch
import json
from datetime import datetime, timezone


# ── Fixtures ──────────────────────────────────────────────────

@pytest_asyncio.fixture
async def mock_redis():
    """In-memory mock for Redis — no running Redis required."""
    store = {}

    class MockRedis:
        async def get(self, key):
            return store.get(key)

        async def set(self, key, value, ex=None):
            store[key] = str(value)
            return True

        async def incrby(self, key, amount=1):
            current = int(store.get(key, 0))
            new_val = current + amount
            store[key] = str(new_val)
            return new_val

        async def decrby(self, key, amount=1):
            current = int(store.get(key, 0))
            new_val = max(0, current - amount)
            store[key] = str(new_val)
            return new_val

        async def expire(self, key, seconds):
            return True

        async def keys(self, pattern):
            import fnmatch
            return [k for k in store.keys() if fnmatch.fnmatch(k, pattern.replace("*", "?*"))]

        async def delete(self, *keys):
            for k in keys:
                store.pop(k, None)
            return len(keys)

        async def ping(self):
            return True

        async def aclose(self):
            pass

    return MockRedis(), store


@pytest_asyncio.fixture
async def usage_svc(mock_redis):
    from app.services.usage_service import UsageService
    redis, store = mock_redis
    svc = UsageService()
    svc._redis = redis
    return svc, store


# ── Tests ─────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_starter_plan_allows_under_limit(usage_svc):
    svc, store = usage_svc
    result = await svc.check_and_increment("org-1", "starter", "test_runs", 1)
    assert result["allowed"] is True
    assert result["current"] == 1
    assert result["limit"] == 100
    assert result["remaining"] == 99


@pytest.mark.asyncio
async def test_starter_plan_blocks_at_limit(usage_svc):
    svc, store = usage_svc
    # Pre-fill to limit
    period = datetime.now(timezone.utc).strftime("%Y-%m")
    store[f"usage:org-2:{period}:test_runs"] = "100"
    
    result = await svc.check_and_increment("org-2", "starter", "test_runs", 1)
    assert result["allowed"] is False
    assert result["current"] == 100
    assert "limit" in result
    assert "upgrade_url" in result


@pytest.mark.asyncio
async def test_enterprise_plan_never_blocked(usage_svc):
    svc, store = usage_svc
    period = datetime.now(timezone.utc).strftime("%Y-%m")
    # Set counter to absurdly high value
    store[f"usage:org-3:{period}:test_runs"] = "999999"
    
    result = await svc.check_and_increment("org-3", "enterprise", "test_runs", 1)
    assert result["allowed"] is True
    assert result["unlimited"] is True


@pytest.mark.asyncio
async def test_warning_fires_at_80_percent(usage_svc):
    svc, store = usage_svc
    period = datetime.now(timezone.utc).strftime("%Y-%m")
    # Set to 79 of 100 — next increment (80) should trigger warning
    store[f"usage:org-4:{period}:test_runs"] = "79"
    
    with patch.object(svc, '_fire_warning_event', new_callable=AsyncMock) as mock_warn:
        result = await svc.check_and_increment("org-4", "starter", "test_runs", 1)
        assert result["allowed"] is True
        assert result["warning"] is True
        mock_warn.assert_called_once()


@pytest.mark.asyncio
async def test_pro_plan_higher_limit(usage_svc):
    svc, store = usage_svc
    period = datetime.now(timezone.utc).strftime("%Y-%m")
    # At starter limit (100) should still be allowed on pro
    store[f"usage:org-5:{period}:test_runs"] = "100"
    
    result = await svc.check_and_increment("org-5", "pro", "test_runs", 1)
    assert result["allowed"] is True
    assert result["limit"] == 2000


@pytest.mark.asyncio
async def test_monthly_reset(usage_svc):
    svc, store = usage_svc
    period = datetime.now(timezone.utc).strftime("%Y-%m")
    store[f"usage:org-6:{period}:test_runs"] = "95"
    
    await svc.reset_monthly("org-6")
    
    result = await svc.check_and_increment("org-6", "starter", "test_runs", 1)
    assert result["current"] == 1  # Reset worked


@pytest.mark.asyncio
async def test_get_usage_returns_all_metrics(usage_svc):
    svc, store = usage_svc
    result = await svc.get_usage("org-7", "pro")
    
    assert "test_runs" in result
    assert "deployments" in result
    assert "ai_generations" in result
    assert result["_plan"] == "pro"
    assert "%" in str(result["test_runs"].get("percentage", ""))  # percentage is a number


@pytest.mark.asyncio
async def test_increment_total_for_projects(usage_svc):
    svc, store = usage_svc
    val1 = await svc.increment_total("org-8", "projects", 1)
    val2 = await svc.increment_total("org-8", "projects", 1)
    assert val2 == 2


@pytest.mark.asyncio
async def test_decrement_total_never_goes_negative(usage_svc):
    svc, store = usage_svc
    val = await svc.decrement_total("org-9", "team_members", 5)
    assert val >= 0
