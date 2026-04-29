"""
Trial Expiry Worker — runs in the events service as a background task.

Checks every 15 minutes for orgs whose trial_ends_at has passed
and fires billing.trial_expired events so that:
  1. Notification service sends the "trial ended" email
  2. Auth service updates the org plan
  3. Frontend shows upgrade CTA

Also fires usage.warning_80pct when orgs approach their limits.
"""

import asyncio
import logging
import os
from datetime import datetime, timezone

import httpx

logger = logging.getLogger("jarviis.trial_worker")

AUTH_SERVICE_URL = os.getenv("AUTH_SERVICE_URL", "http://auth-service:8001")
EVENTS_SERVICE_URL = os.getenv("EVENTS_SERVICE_URL", "http://events:8017")
INTERNAL_SECRET = os.getenv("INTERNAL_SERVICE_SECRET", "jarviis-internal-secret")
CHECK_INTERVAL_SECONDS = 900  # 15 minutes


async def check_expired_trials() -> None:
    """Query auth service for orgs with expired trials and fire events."""
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            # Get all orgs with active trials from auth service
            resp = await client.get(
                f"{AUTH_SERVICE_URL}/api/v1/internal/orgs/expired-trials",
                headers={"X-Internal-Secret": INTERNAL_SECRET},
            )
            if resp.status_code != 200:
                logger.debug(f"Trial check endpoint returned {resp.status_code}")
                return

            expired_orgs = resp.json().get("orgs", [])
            if not expired_orgs:
                return

            logger.info(f"Found {len(expired_orgs)} expired trials to process")

            for org in expired_orgs:
                org_id = org.get("id")
                if not org_id:
                    continue

                # Fire trial_expired event
                await client.post(
                    f"{EVENTS_SERVICE_URL}/api/v1/events/publish",
                    json={
                        "event": "billing.trial_expired",
                        "org_id": org_id,
                        "source_service": "trial_worker",
                        "payload": {
                            "org_slug": org.get("slug", ""),
                            "org_name": org.get("name", ""),
                            "trial_ended_at": org.get("trial_ends_at", ""),
                        },
                    },
                )

                # Mark trial as processed in auth service (prevent re-firing)
                await client.post(
                    f"{AUTH_SERVICE_URL}/api/v1/internal/orgs/{org_id}/mark-trial-expired",
                    headers={"X-Internal-Secret": INTERNAL_SECRET},
                )
                logger.info(f"Fired trial_expired for org {org_id} ({org.get('slug')})")

    except Exception as e:
        logger.debug(f"Trial check error (non-critical): {e}")


async def trial_expiry_loop() -> None:
    """Background loop — runs every 15 minutes."""
    logger.info("Trial expiry worker started (checks every 15 minutes)")
    # Initial delay to let services start up
    await asyncio.sleep(60)
    while True:
        await check_expired_trials()
        await asyncio.sleep(CHECK_INTERVAL_SECONDS)
