"""JarviisAI — Feature Flags Service"""

import os
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi import Header
from pydantic import BaseModel
from typing import Optional, Dict, Any
import logging, os, json
from app.core.logging_config import configure_logging
import redis.asyncio as aioredis

logging.basicConfig(level=os.getenv("LOG_LEVEL", "info").upper(),
                    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s")
logger = logging.getLogger("jarviis.flags")

REDIS_URL = os.getenv("REDIS_URL", "redis://:redis_secret@redis:6379/19")

# Default flag definitions — shipped in code, overridden via Redis
DEFAULT_FLAGS: Dict[str, dict] = {
    "cobol_testing":        {"enabled": True,  "rollout_pct": 100, "plans": ["team", "enterprise"]},
    "mobile_testing":       {"enabled": True,  "rollout_pct": 100, "plans": ["team", "enterprise"]},
    "visual_regression":    {"enabled": True,  "rollout_pct": 100, "plans": ["pro", "team", "enterprise"]},
    "api_testing":          {"enabled": True,  "rollout_pct": 100, "plans": ["pro", "team", "enterprise"]},
    "jarviis_ai_assistant": {"enabled": True,  "rollout_pct": 100, "plans": ["team", "enterprise"]},
    "enterprise_sso":       {"enabled": True,  "rollout_pct": 100, "plans": ["enterprise"]},
    "scim_provisioning":    {"enabled": False, "rollout_pct": 0,   "plans": ["enterprise"]},
    "ai_test_healing":      {"enabled": True,  "rollout_pct": 100, "plans": ["pro", "team", "enterprise"]},
    "advanced_analytics":   {"enabled": True,  "rollout_pct": 100, "plans": ["pro", "team", "enterprise"]},
    "compliance_exports":   {"enabled": True,  "rollout_pct": 100, "plans": ["team", "enterprise"]},
    "maintenance_mode":     {"enabled": False, "rollout_pct": 100, "plans": []},
    "new_dashboard_v2":     {"enabled": False, "rollout_pct": 10,  "plans": ["pro", "team", "enterprise"]},
}

_redis: Optional[aioredis.Redis] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _redis
    _redis = aioredis.from_url(REDIS_URL, encoding="utf-8", decode_responses=True)
    logger.info("🚩 Feature Flags Service ready")
    yield
    if _redis:
        await _redis.aclose()


APP_URL = os.getenv("APP_URL", "http://localhost:3000")
INTERNAL_SECRET = os.getenv("INTERNAL_SERVICE_SECRET", "jarviis-internal-secret")
INTERNAL_ORIGINS = [
    APP_URL,
    "http://localhost:3000",
    "http://jarviis-frontend:3000",
    "http://api-gateway:8000",
    "http://localhost:8000",
]

from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

limiter = Limiter(key_func=get_remote_address, default_limits=["200/minute"])


class SecurityHeadersMiddleware:
    """Add security headers to every response."""
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_with_headers(message):
            if message["type"] == "http.response.start":
                headers = dict(message.get("headers", []))
                security_headers = [
                    (b"x-content-type-options", b"nosniff"),
                    (b"x-frame-options", b"DENY"),
                    (b"x-xss-protection", b"1; mode=block"),
                    (b"referrer-policy", b"strict-origin-when-cross-origin"),
                    (b"strict-transport-security", b"max-age=31536000; includeSubDomains"),
                ]
                existing = {h[0] for h in message.get("headers", [])}
                new_headers = list(message.get("headers", []))
                for h, v in security_headers:
                    if h not in existing:
                        new_headers.append((h, v))
                message = {**message, "headers": new_headers}
            await send(message)

        await self.app(scope, receive, send_with_headers)

app = FastAPI(title="JarviisAI Feature Flags", version="1.0.0", lifespan=lifespan)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(CORSMiddleware, allow_origins=INTERNAL_ORIGINS, allow_credentials=True, allow_methods=["*"], allow_headers=["*"])


async def _get_flag(flag_name: str, org_id: Optional[str] = None) -> Optional[dict]:
    """Get flag config, checking org override then global then default."""
    if _redis:
        # Org-level override
        if org_id:
            override = await _redis.get(f"flag:org:{org_id}:{flag_name}")
            if override:
                return json.loads(override)
        # Global override
        global_val = await _redis.get(f"flag:global:{flag_name}")
        if global_val:
            return json.loads(global_val)
    # Code default
    return DEFAULT_FLAGS.get(flag_name)


class FlagEvalRequest(BaseModel):
    org_id: str
    plan: str = "starter"


class FlagSetRequest(BaseModel):
    enabled: bool
    rollout_pct: int = 100
    plans: list = []
    org_id: Optional[str] = None   # If set, org-level override


@app.get("/health")
async def health():
    return {"service": "feature-flags", "status": "ok", "flags": len(DEFAULT_FLAGS)}

@app.get("/metrics", include_in_schema=False)
async def metrics():
    """Prometheus metrics endpoint."""
    try:
        from prometheus_client import generate_latest, CONTENT_TYPE_LATEST, REGISTRY
        from fastapi.responses import Response
        return Response(content=generate_latest(REGISTRY), media_type=CONTENT_TYPE_LATEST)
    except ImportError:
        from fastapi.responses import PlainTextResponse
        return PlainTextResponse("# prometheus_client not installed\n")



@app.post("/api/v1/flags/{flag_name}/evaluate")
async def evaluate_flag(flag_name: str, data: FlagEvalRequest):
    """Evaluate if a flag is enabled for a given org + plan."""
    flag = await _get_flag(flag_name, data.org_id)
    if not flag:
        return {"flag": flag_name, "enabled": False, "reason": "unknown_flag"}

    # Maintenance mode — always check first
    if flag_name != "maintenance_mode":
        maintenance = await _get_flag("maintenance_mode")
        if maintenance and maintenance.get("enabled"):
            return {"flag": flag_name, "enabled": False, "reason": "maintenance_mode"}

    if not flag.get("enabled", False):
        return {"flag": flag_name, "enabled": False, "reason": "flag_disabled"}

    # Plan check
    allowed_plans = flag.get("plans", [])
    if allowed_plans and data.plan.lower() not in [p.lower() for p in allowed_plans]:
        return {"flag": flag_name, "enabled": False, "reason": "plan_not_included",
                "required_plans": allowed_plans}

    return {"flag": flag_name, "enabled": True, "reason": "ok"}


@app.get("/api/v1/flags/evaluate-all")
async def evaluate_all_flags(org_id: str, plan: str = "starter"):
    """Evaluate ALL flags for an org — used by frontend on load."""
    results = {}
    for flag_name in DEFAULT_FLAGS:
        result = await evaluate_flag(flag_name, FlagEvalRequest(org_id=org_id, plan=plan))
        results[flag_name] = result["enabled"]
    return results


@app.get("/api/v1/flags")
async def list_flags():
    """Admin: list all flags and their current state."""
    return DEFAULT_FLAGS


@app.post("/api/v1/flags/{flag_name}")
async def set_flag(
    flag_name: str,
    data: FlagSetRequest,
    x_internal_secret: Optional[str] = Header(None),
):
    """Admin: set a flag globally or for a specific org. Requires internal secret."""
    if x_internal_secret != INTERNAL_SECRET:
        from fastapi import HTTPException
        raise HTTPException(status_code=403, detail="Admin access required")
    if not _redis:
        raise HTTPException(status_code=503, detail="Redis not available")

    flag_data = {"enabled": data.enabled, "rollout_pct": data.rollout_pct, "plans": data.plans}

    if data.org_id:
        await _redis.set(f"flag:org:{data.org_id}:{flag_name}", json.dumps(flag_data))
        logger.info(f"Flag {flag_name} set to {data.enabled} for org {data.org_id}")
    else:
        await _redis.set(f"flag:global:{flag_name}", json.dumps(flag_data))
        logger.info(f"Global flag {flag_name} set to {data.enabled}")

    return {"flag": flag_name, "set": True, "scope": "org" if data.org_id else "global"}


@app.delete("/api/v1/flags/{flag_name}")
async def reset_flag(
    flag_name: str,
    org_id: Optional[str] = None,
    x_internal_secret: Optional[str] = Header(None),
):
    """Reset a flag override. Requires internal secret."""
    if x_internal_secret != INTERNAL_SECRET:
        from fastapi import HTTPException
        raise HTTPException(status_code=403, detail="Admin access required")
    if _redis:
        if org_id:
            await _redis.delete(f"flag:org:{org_id}:{flag_name}")
        else:
            await _redis.delete(f"flag:global:{flag_name}")
    return {"flag": flag_name, "reset": True}
