"""
JarviisAI Event Bus Service.

Central event backbone for all inter-service communication.
All services publish here. All consumers subscribe here.
Backed by Redis Streams (persistent, replayable) + pub/sub for real-time.

Event schema: {event, org_id, project_id, actor_id, payload, timestamp, trace_id}

Events:
  test.started | test.completed | test.failed | test.healing_applied
  deploy.started | deploy.completed | deploy.rolled_back | deploy.failed
  security.scan_completed | security.issue_critical
  billing.plan_changed | billing.trial_started | billing.trial_expired
  billing.payment_failed | billing.subscription_cancelled
  usage.warning_80pct | usage.limit_reached | usage.overage
  org.member_added | org.member_removed | org.created
  project.created | project.deleted
  incident.created | incident.resolved
"""

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Callable, Awaitable
import redis.asyncio as aioredis
from fastapi import FastAPI
from contextlib import asynccontextmanager
from pydantic import BaseModel
import os

logger = logging.getLogger("jarviis.events")

REDIS_URL = os.getenv("REDIS_URL", "redis://:redis_secret@redis:6379/15")
STREAM_KEY = "jarviis:events"
MAX_STREAM_LEN = 100_000  # Keep last 100K events


class JarviisEvent(BaseModel):
    event: str
    org_id: Optional[str] = None
    project_id: Optional[str] = None
    actor_id: Optional[str] = None
    payload: Dict[str, Any] = {}
    timestamp: str = ""
    trace_id: str = ""
    source_service: str = ""

    def __init__(self, **data):
        if not data.get("timestamp"):
            data["timestamp"] = datetime.now(timezone.utc).isoformat()
        if not data.get("trace_id"):
            data["trace_id"] = str(uuid.uuid4())
        super().__init__(**data)


class EventBus:
    def __init__(self):
        self._redis: Optional[aioredis.Redis] = None
        self._consumers: Dict[str, List[Callable]] = {}

    async def connect(self):
        self._redis = aioredis.from_url(REDIS_URL, encoding="utf-8", decode_responses=True)
        await self._redis.ping()
        logger.info("Event bus connected to Redis")

    async def disconnect(self):
        if self._redis:
            await self._redis.aclose()

    async def publish(self, event: JarviisEvent) -> str:
        """Publish an event to the stream. Returns the stream entry ID."""
        if not self._redis:
            return ""
        try:
            data = event.model_dump()
            # Redis streams require flat string values
            flat = {k: json.dumps(v) if isinstance(v, dict) else str(v) for k, v in data.items()}
            entry_id = await self._redis.xadd(
                STREAM_KEY, flat, maxlen=MAX_STREAM_LEN, approximate=True
            )
            # Also pub/sub for real-time consumers
            await self._redis.publish(f"jarviis:events:{event.event}", json.dumps(data))
            return entry_id
        except Exception as e:
            logger.error(f"Event publish failed: {e}")
            return ""

    async def publish_dict(self, event: str, org_id: str = None, project_id: str = None,
                           actor_id: str = None, source: str = "", **payload) -> str:
        """Convenience method for publishing events."""
        return await self.publish(JarviisEvent(
            event=event,
            org_id=org_id,
            project_id=project_id,
            actor_id=actor_id,
            source_service=source,
            payload=payload,
        ))

    async def get_events(
        self,
        org_id: Optional[str] = None,
        event_types: Optional[List[str]] = None,
        since: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict]:
        """Query events from the stream with optional filters."""
        if not self._redis:
            return []
        try:
            start = since or "-"
            entries = await self._redis.xrange(STREAM_KEY, start, "+", count=limit * 5)
            results = []
            for entry_id, fields in entries:
                evt = {k: (json.loads(v) if v.startswith("{") or v.startswith("[") else v)
                       for k, v in fields.items()}
                evt["_stream_id"] = entry_id
                if org_id and evt.get("org_id") != org_id:
                    continue
                if event_types and evt.get("event") not in event_types:
                    continue
                results.append(evt)
                if len(results) >= limit:
                    break
            return results
        except Exception as e:
            logger.error(f"Event query failed: {e}")
            return []

    async def get_stats(self) -> Dict:
        """Stream statistics."""
        if not self._redis:
            return {}
        try:
            info = await self._redis.xinfo_stream(STREAM_KEY)
            return {
                "length": info.get("length", 0),
                "first_entry": info.get("first-entry"),
                "last_entry": info.get("last-entry"),
            }
        except Exception:
            return {"length": 0}


event_bus = EventBus()
