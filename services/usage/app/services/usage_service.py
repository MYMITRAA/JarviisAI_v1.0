"""
JarviisAI Usage Metering Service.

THE most important new service. Closes the billing gap.

What it does:
1. Tracks usage counters per org per billing period (Redis + PostgreSQL)
2. Enforces limits BEFORE runs/deploys start (hard block)
3. Fires warning events at 80% of limit
4. Fires limit_reached events at 100%
5. Exposes usage dashboard data

Counters tracked:
  - test_runs (monthly)
  - deployments (monthly)
  - ai_test_generations (monthly)
  - security_scans (monthly)
  - api_test_runs (monthly)
  - projects (total)
  - team_members (total)

Plan limits (copied from billing service for enforcement):
  Starter: 100 runs, 3 projects, 1 member, 10 deploys
  Pro:     2000 runs, 20 projects, 5 members, 200 deploys
  Team:    10000 runs, 100 projects, 25 members, 1000 deploys
  Enterprise: unlimited
"""

import json
import logging
import os
from datetime import datetime, timezone
from typing import Dict, Optional, Tuple
import redis.asyncio as aioredis

logger = logging.getLogger("jarviis.usage")

REDIS_URL = os.getenv("REDIS_URL", "redis://:redis_secret@redis:6379/16")
EVENTS_SERVICE_URL = os.getenv("EVENTS_SERVICE_URL", "http://events:8017")

# Plan limits — single source of truth
PLAN_LIMITS = {
    "free":       {"test_runs": 100,   "projects": 3,   "team_members": 5,  "deployments": 10,  "ai_generations": 20,  "security_scans": 5},
    "starter":    {"test_runs": 100,   "projects": 3,   "team_members": 1,  "deployments": 10,  "ai_generations": 20,  "security_scans": 5},
    "pro":        {"test_runs": 2000,  "projects": 20,  "team_members": 5,  "deployments": 200, "ai_generations": 500, "security_scans": 50},
    "team":       {"test_runs": 10000, "projects": 100, "team_members": 25, "deployments": 1000,"ai_generations": 2000,"security_scans": 200},
    "enterprise": {"test_runs": -1,    "projects": -1,  "team_members": -1, "deployments": -1,  "ai_generations": -1,  "security_scans": -1},
}

# Trial plan — 2-day trial with Pro limits
TRIAL_LIMITS = PLAN_LIMITS["pro"]

WARNING_THRESHOLD = 0.80  # 80% = send warning


class UsageService:

    def __init__(self):
        self._redis: Optional[aioredis.Redis] = None

    async def connect(self):
        self._redis = aioredis.from_url(REDIS_URL, encoding="utf-8", decode_responses=True)

    async def disconnect(self):
        if self._redis:
            await self._redis.aclose()

    # ── Key helpers ───────────────────────────────────────────

    def _monthly_key(self, org_id: str, metric: str) -> str:
        """Redis key for monthly counter: usage:{org_id}:{YYYY-MM}:{metric}"""
        period = datetime.now(timezone.utc).strftime("%Y-%m")
        return f"usage:{org_id}:{period}:{metric}"

    def _total_key(self, org_id: str, metric: str) -> str:
        """Redis key for total (non-resetting) counter."""
        return f"usage_total:{org_id}:{metric}"

    # ── Core check-and-increment ──────────────────────────────

    async def check_and_increment(
        self,
        org_id: str,
        plan: str,
        metric: str,
        increment_by: int = 1,
    ) -> Dict:
        """
        The main enforcement method. Call this BEFORE allowing any operation.

        Returns:
          allowed: bool — False = block the operation
          current: int — current usage this period
          limit: int — plan limit (-1 = unlimited)
          remaining: int — how many left
          warning: bool — at or above 80% threshold
        """
        plan_key = plan.lower().replace("-", "_")
        limits = PLAN_LIMITS.get(plan_key, PLAN_LIMITS["starter"])
        limit = limits.get(metric, 0)

        # Unlimited
        if limit == -1:
            current = await self._get_counter(org_id, metric)
            await self._increment(org_id, metric)
            return {"allowed": True, "current": current + increment_by, "limit": -1,
                    "remaining": -1, "warning": False, "unlimited": True}

        # Get current count
        current = await self._get_counter(org_id, metric)

        # Hard limit check
        if current + increment_by > limit:
            await self._fire_limit_event(org_id, metric, current, limit)
            return {
                "allowed": False,
                "current": current,
                "limit": limit,
                "remaining": max(0, limit - current),
                "warning": True,
                "unlimited": False,
                "error": f"Plan limit reached: {current}/{limit} {metric} used this month. Upgrade to continue.",
                "upgrade_url": "/settings/billing",
            }

        # Increment
        new_count = await self._increment(org_id, metric, increment_by)

        # Warning check
        warning = False
        if limit > 0 and new_count / limit >= WARNING_THRESHOLD:
            warning = True
            await self._fire_warning_event(org_id, metric, new_count, limit)

        return {
            "allowed": True,
            "current": new_count,
            "limit": limit,
            "remaining": max(0, limit - new_count),
            "warning": warning,
            "unlimited": False,
        }

    async def get_usage(self, org_id: str, plan: str) -> Dict:
        """Get full usage summary for an org."""
        plan_key = plan.lower()
        limits = PLAN_LIMITS.get(plan_key, PLAN_LIMITS["starter"])
        result = {}

        for metric, limit in limits.items():
            if metric in ("projects", "team_members"):
                current = await self._get_total(org_id, metric)
            else:
                current = await self._get_counter(org_id, metric)

            pct = round(current / limit * 100, 1) if limit > 0 else 0
            result[metric] = {
                "current": current,
                "limit": limit,
                "percentage": pct,
                "unlimited": limit == -1,
                "warning": pct >= 80 and limit != -1,
                "over": current > limit and limit != -1,
            }

        # Get period info
        period = datetime.now(timezone.utc).strftime("%Y-%m")
        result["_period"] = period
        result["_plan"] = plan
        return result

    async def set_total(self, org_id: str, metric: str, value: int) -> None:
        """Set a total counter (for projects, members — not time-bounded)."""
        if self._redis:
            await self._redis.set(self._total_key(org_id, metric), value)

    async def increment_total(self, org_id: str, metric: str, by: int = 1) -> int:
        """Increment a total counter."""
        if self._redis:
            return await self._redis.incrby(self._total_key(org_id, metric), by)
        return 0

    async def decrement_total(self, org_id: str, metric: str, by: int = 1) -> int:
        """Decrement a total counter (member removed, project deleted)."""
        if self._redis:
            result = await self._redis.decrby(self._total_key(org_id, metric), by)
            return max(0, result)
        return 0

    async def reset_monthly(self, org_id: str) -> None:
        """Reset monthly counters (called at billing period renewal)."""
        if not self._redis:
            return
        period = datetime.now(timezone.utc).strftime("%Y-%m")
        pattern = f"usage:{org_id}:{period}:*"
        keys = await self._redis.keys(pattern)
        if keys:
            await self._redis.delete(*keys)
        logger.info(f"Reset monthly usage for org {org_id}")

    async def get_all_orgs_usage(self) -> Dict:
        """Admin view — all org usage summaries (for health scoring)."""
        if not self._redis:
            return {}
        pattern = "usage:*"
        keys = await self._redis.keys(pattern)
        orgs = {}
        for key in keys:
            parts = key.split(":")
            if len(parts) >= 4:
                org_id = parts[1]
                metric = parts[3]
                val = await self._redis.get(key)
                if org_id not in orgs:
                    orgs[org_id] = {}
                orgs[org_id][metric] = int(val or 0)
        return orgs

    # ── Private helpers ───────────────────────────────────────

    async def _get_counter(self, org_id: str, metric: str) -> int:
        if not self._redis:
            return 0
        val = await self._redis.get(self._monthly_key(org_id, metric))
        return int(val or 0)

    async def _get_total(self, org_id: str, metric: str) -> int:
        if not self._redis:
            return 0
        val = await self._redis.get(self._total_key(org_id, metric))
        return int(val or 0)

    async def _increment(self, org_id: str, metric: str, by: int = 1) -> int:
        if not self._redis:
            return 0
        key = self._monthly_key(org_id, metric)
        new_val = await self._redis.incrby(key, by)
        # Set TTL to 35 days (covers full billing period + buffer)
        await self._redis.expire(key, 35 * 24 * 3600)
        return new_val

    async def _fire_warning_event(self, org_id: str, metric: str, current: int, limit: int) -> None:
        import httpx
        pct = round(current / limit * 100)
        try:
            async with httpx.AsyncClient(timeout=2.0) as client:
                await client.post(f"{EVENTS_SERVICE_URL}/api/v1/events/publish", json={
                    "event": "usage.warning_80pct",
                    "org_id": org_id,
                    "source_service": "usage",
                    "payload": {"metric": metric, "current": current, "limit": limit, "pct": pct},
                })
        except Exception:
            pass

    async def _fire_limit_event(self, org_id: str, metric: str, current: int, limit: int) -> None:
        import httpx
        try:
            async with httpx.AsyncClient(timeout=2.0) as client:
                await client.post(f"{EVENTS_SERVICE_URL}/api/v1/events/publish", json={
                    "event": "usage.limit_reached",
                    "org_id": org_id,
                    "source_service": "usage",
                    "payload": {"metric": metric, "current": current, "limit": limit},
                })
        except Exception:
            pass


usage_service = UsageService()
