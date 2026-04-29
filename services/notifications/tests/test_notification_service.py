"""Tests for the Notifications Service."""
import pytest
import pytest_asyncio
import json
from unittest.mock import AsyncMock, patch, MagicMock


@pytest_asyncio.fixture
async def mock_redis():
    store = {}
    lists = {}
    sets = {}

    class MockRedis:
        async def set(self, key, value, ex=None): store[key] = value; return True
        async def get(self, key): return store.get(key)
        async def lpush(self, key, value):
            lists.setdefault(key, []).insert(0, value)
            return len(lists[key])
        async def ltrim(self, key, start, end):
            if key in lists:
                lists[key] = lists[key][start:end+1]
        async def lrange(self, key, start, end):
            return lists.get(key, [])[start:end+1 if end >= 0 else None]
        async def llen(self, key): return len(lists.get(key, []))
        async def sadd(self, key, *values):
            sets.setdefault(key, set()).update(values)
            return len(values)
        async def scard(self, key): return len(sets.get(key, set()))
        async def expire(self, key, seconds): return True
        async def ping(self): return True
        async def aclose(self): pass

    return MockRedis()


@pytest_asyncio.fixture
async def svc(mock_redis):
    from app.services.notification_service import NotificationService
    s = NotificationService()
    s._redis = mock_redis
    return s


@pytest.mark.asyncio
async def test_in_app_notification_stored(svc):
    await svc._send_in_app("org-1", "test.failed", "Tests failed: 5/50", {})
    notifs = await svc.get_in_app_notifications("org-1")
    assert len(notifs) == 1
    assert notifs[0]["event"] == "test.failed"
    assert "Tests failed" in notifs[0]["message"]


@pytest.mark.asyncio
async def test_unread_count_increments(svc):
    await svc._send_in_app("org-2", "test.failed", "msg1", {})
    await svc._send_in_app("org-2", "deploy.failed", "msg2", {})
    count = await svc.get_unread_count("org-2")
    assert count == 2


@pytest.mark.asyncio
async def test_mark_read_decrements_unread(svc):
    await svc._send_in_app("org-3", "test.failed", "msg", {})
    notifs = await svc.get_in_app_notifications("org-3")
    notif_id = notifs[0]["id"]
    await svc.mark_read("org-3", notif_id)
    count = await svc.get_unread_count("org-3")
    assert count == 0


@pytest.mark.asyncio
async def test_message_format_test_failed(svc):
    msg = svc._format_message("test.failed", {"passed": 45, "failed": 5, "total": 50, "pass_rate": 90.0})
    assert "5" in msg
    assert "50" in msg


@pytest.mark.asyncio
async def test_message_format_trial_expired(svc):
    msg = svc._format_message("billing.trial_expired", {})
    assert "trial" in msg.lower() or "2-day" in msg.lower()


@pytest.mark.asyncio
async def test_message_format_usage_warning(svc):
    msg = svc._format_message("usage.warning_80pct", {"pct": 84, "metric": "test_runs", "current": 84, "limit": 100})
    assert "84" in msg


@pytest.mark.asyncio
async def test_handle_event_no_config_does_in_app(svc):
    """With no channel config, at least in_app notification is stored."""
    await svc.handle_event("test.failed", "org-4", {"passed": 0, "failed": 10, "total": 10, "pass_rate": 0})
    notifs = await svc.get_in_app_notifications("org-4")
    assert len(notifs) >= 1


@pytest.mark.asyncio
async def test_slack_notification_sent(svc):
    await svc.save_org_config("org-5", {
        "slack_webhook_url": "https://hooks.slack.com/test",
        "notification_email": None,
    })
    with patch("httpx.AsyncClient") as mock_client:
        mock_instance = AsyncMock()
        mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
        mock_instance.__aexit__ = AsyncMock(return_value=None)
        mock_instance.post = AsyncMock()
        mock_client.return_value = mock_instance
        await svc._send_slack("https://hooks.slack.com/test", "test.failed", "Tests failed", {})
        mock_instance.post.assert_called_once()
