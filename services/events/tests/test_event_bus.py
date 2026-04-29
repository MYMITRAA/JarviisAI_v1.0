"""Tests for the Event Bus Service."""
import pytest
import pytest_asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch


@pytest_asyncio.fixture
async def mock_redis():
    stream_data = []
    pubsub_messages = {}

    class MockRedis:
        async def ping(self): return True
        async def aclose(self): pass
        async def xadd(self, key, data, maxlen=None, approximate=None):
            entry_id = f"1000-{len(stream_data)}"
            stream_data.append((entry_id, data))
            return entry_id
        async def xrange(self, key, start="-", end="+", count=None):
            return stream_data
        async def xinfo_stream(self, key):
            return {"length": len(stream_data), "first-entry": None, "last-entry": None}
        async def publish(self, channel, message): return 1

    return MockRedis()


@pytest_asyncio.fixture
async def bus(mock_redis):
    from app.services.event_bus import EventBus
    b = EventBus()
    b._redis = mock_redis
    return b


@pytest.mark.asyncio
async def test_publish_returns_entry_id(bus):
    from app.services.event_bus import JarviisEvent
    evt = JarviisEvent(event="test.completed", org_id="org-1", payload={"pass_rate": 97.0})
    entry_id = await bus.publish(evt)
    assert entry_id is not None
    assert entry_id != ""


@pytest.mark.asyncio
async def test_publish_dict_convenience(bus):
    entry_id = await bus.publish_dict("test.failed", org_id="org-1", pass_rate=45.0)
    assert entry_id is not None


@pytest.mark.asyncio
async def test_get_events_with_org_filter(bus):
    from app.services.event_bus import JarviisEvent
    await bus.publish(JarviisEvent(event="test.completed", org_id="org-A", payload={}))
    await bus.publish(JarviisEvent(event="test.failed",    org_id="org-B", payload={}))
    events = await bus.get_events(org_id="org-A")
    assert all(e["org_id"] == "org-A" for e in events if e.get("org_id"))


@pytest.mark.asyncio
async def test_event_has_timestamp_and_trace_id(bus):
    from app.services.event_bus import JarviisEvent
    evt = JarviisEvent(event="deploy.started", org_id="org-1")
    assert evt.timestamp != ""
    assert evt.trace_id != ""


@pytest.mark.asyncio
async def test_get_stats(bus):
    stats = await bus.get_stats()
    assert "length" in stats


@pytest.mark.asyncio
async def test_publish_never_raises_on_redis_error(bus):
    bus._redis = None  # Simulate disconnected Redis
    entry_id = await bus.publish_dict("test.completed", org_id="org-1")
    assert entry_id == ""  # Returns empty string, never raises
