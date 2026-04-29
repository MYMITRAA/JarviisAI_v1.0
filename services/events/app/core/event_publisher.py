"""
Shared event publisher — import this in any JarviisAI service to fire events.

Usage:
    from app.core.event_publisher import publish_event
    await publish_event("test.completed", org_id=org_id, project_id=pid,
                        status="passed", pass_rate=97.2, total_tests=89)
"""
import json
import logging
import os
from typing import Any, Optional
import httpx

logger = logging.getLogger("jarviis.event_publisher")

EVENTS_SERVICE_URL = os.getenv("EVENTS_SERVICE_URL", "http://events:8017")
SOURCE_SERVICE = os.getenv("SERVICE_NAME", "unknown")


async def publish_event(
    event: str,
    org_id: Optional[str] = None,
    project_id: Optional[str] = None,
    actor_id: Optional[str] = None,
    **payload: Any,
) -> None:
    """Fire-and-forget event publish. Never blocks the caller."""
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            await client.post(
                f"{EVENTS_SERVICE_URL}/api/v1/events/publish",
                json={
                    "event": event,
                    "org_id": org_id,
                    "project_id": project_id,
                    "actor_id": actor_id,
                    "source_service": SOURCE_SERVICE,
                    "payload": payload,
                },
            )
    except Exception as e:
        # Never crash the caller due to event bus issues
        logger.debug(f"Event publish skipped ({event}): {e}")
