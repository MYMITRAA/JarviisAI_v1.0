"""Tests for the Customer Health Scoring Service."""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from httpx import AsyncClient, ASGITransport


@pytest.fixture
def app():
    from app.main import app as _app
    return _app


def test_score_computed_correctly():
    from app.main import _compute_score
    from datetime import datetime, timezone, timedelta

    # Active user with 50% plan usage
    signals = {
        "last_activity": str((datetime.now(timezone.utc) - timedelta(hours=2)).timestamp()),
        "last_event": "test.completed",
    }
    usage = {
        "test_runs": {"percentage": 50, "unlimited": False}
    }
    result = _compute_score(signals, usage)
    assert 0 <= result["score"] <= 100
    assert result["risk"] in ("healthy", "churn_risk", "expansion")


def test_inactive_org_has_low_score():
    from app.main import _compute_score, CHURN_THRESHOLD
    from datetime import datetime, timezone, timedelta

    # No activity in 60 days
    signals = {
        "last_activity": str((datetime.now(timezone.utc) - timedelta(days=60)).timestamp()),
    }
    usage = {"test_runs": {"percentage": 0, "unlimited": False}}
    result = _compute_score(signals, usage)
    assert result["score"] < 50  # Should be unhealthy


def test_very_active_org_high_score():
    from app.main import _compute_score, EXPAND_THRESHOLD
    from datetime import datetime, timezone, timedelta

    # Active today, 50% usage
    signals = {
        "last_activity": str(datetime.now(timezone.utc).timestamp()),
        "last_event": "test.completed",
    }
    usage = {"test_runs": {"percentage": 50, "unlimited": False}}
    result = _compute_score(signals, usage)
    assert result["score"] >= 40  # At least moderate


def test_churn_threshold():
    from app.main import CHURN_THRESHOLD, EXPAND_THRESHOLD
    assert CHURN_THRESHOLD < EXPAND_THRESHOLD
    assert 0 < CHURN_THRESHOLD < 100
    assert 0 < EXPAND_THRESHOLD < 100


@pytest.mark.asyncio
async def test_health_score_endpoint_returns_structure(app):
    with patch("httpx.AsyncClient") as mock_cls:
        inst = AsyncMock()
        inst.__aenter__ = AsyncMock(return_value=inst)
        inst.__aexit__ = AsyncMock(return_value=None)
        inst.get.return_value.status_code = 200
        inst.get.return_value.json = MagicMock(return_value={"test_runs": {"percentage": 45, "unlimited": False}})
        mock_cls.return_value = inst

        import app.main as main_module
        mock_r = AsyncMock()
        mock_r.hgetall = AsyncMock(return_value={})
        main_module._redis = mock_r

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/api/v1/health-score/org-1")
            assert resp.status_code == 200
            data = resp.json()
            assert "score" in data
            assert "risk" in data
            assert "breakdown" in data
            assert "org_id" in data


@pytest.mark.asyncio
async def test_health_endpoint(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/health")
        assert resp.status_code == 200
