"""JarviisAI — Customer Health Scoring Service"""

import os
from contextlib import asynccontextmanager
from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from typing import Optional
import logging, os, json, asyncio
from app.core.logging_config import configure_logging
from datetime import datetime, timezone
import redis.asyncio as aioredis
import httpx

logging.basicConfig(level=os.getenv("LOG_LEVEL", "info").upper(),
                    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s")
logger = logging.getLogger("jarviis.health")

REDIS_URL = os.getenv("REDIS_URL", "redis://:redis_secret@redis:6379/21")
USAGE_URL = os.getenv("USAGE_SERVICE_URL", "http://usage:8018")
ANALYTICS_URL = os.getenv("ANALYTICS_SERVICE_URL", "http://analytics:8020")
_redis: Optional[aioredis.Redis] = None

# Health score weights (total = 100)
SCORE_WEIGHTS = {
    "run_frequency":    20,   # Are they running tests regularly?
    "pass_rate_trend":  20,   # Is quality improving or declining?
    "deploy_activity":  15,   # Are they deploying?
    "feature_adoption": 20,   # Are they using key features?
    "usage_ratio":      15,   # Are they at healthy usage level (not 0, not 100%)?
    "login_recency":    10,   # When did someone last log in?
}

CHURN_THRESHOLD = 40   # Score below this = churn risk
EXPAND_THRESHOLD = 75  # Score above this = expansion opportunity


async def event_consumer():
    """Update health scores on relevant events."""
    redis = aioredis.from_url(REDIS_URL, encoding="utf-8", decode_responses=True)
    pubsub = redis.pubsub()
    await pubsub.subscribe(
        "jarviis:events:test.completed",
        "jarviis:events:test.failed",
        "jarviis:events:deploy.completed",
        "jarviis:events:usage.limit_reached",
    )
    async for message in pubsub.listen():
        if message["type"] != "message":
            continue
        try:
            data = json.loads(message["data"])
            org_id = data.get("org_id")
            if org_id:
                # Recalculate health score on activity
                await _update_org_activity(redis, org_id, data.get("event", ""))
        except Exception:
            pass


async def _update_org_activity(redis, org_id: str, event_type: str) -> None:
    """Update activity signals in Redis for health scoring."""
    now = datetime.now(timezone.utc).timestamp()
    await redis.hset(f"health:signals:{org_id}", mapping={
        "last_activity": str(now),
        "last_event": event_type,
    })
    await redis.expire(f"health:signals:{org_id}", 90 * 24 * 3600)


def _compute_score(signals: dict, usage: dict) -> dict:
    """Compute health score from signals. Returns score (0-100) and breakdown."""
    score = 0
    breakdown = {}

    # Run frequency — based on recent activity
    last_activity = float(signals.get("last_activity", 0))
    days_since_activity = (datetime.now(timezone.utc).timestamp() - last_activity) / 86400 if last_activity else 999
    if days_since_activity <= 1:
        freq_score = SCORE_WEIGHTS["run_frequency"]
    elif days_since_activity <= 3:
        freq_score = int(SCORE_WEIGHTS["run_frequency"] * 0.8)
    elif days_since_activity <= 7:
        freq_score = int(SCORE_WEIGHTS["run_frequency"] * 0.5)
    elif days_since_activity <= 30:
        freq_score = int(SCORE_WEIGHTS["run_frequency"] * 0.2)
    else:
        freq_score = 0
    score += freq_score
    breakdown["run_frequency"] = {"score": freq_score, "max": SCORE_WEIGHTS["run_frequency"],
                                   "signal": f"{int(days_since_activity)}d since last activity"}

    # Usage ratio — healthy = 20-80% of plan
    test_usage = usage.get("test_runs", {})
    pct = test_usage.get("percentage", 0)
    if 20 <= pct <= 80:
        usage_score = SCORE_WEIGHTS["usage_ratio"]
    elif pct < 5:
        usage_score = 0  # Not using at all
    elif pct > 95:
        usage_score = int(SCORE_WEIGHTS["usage_ratio"] * 0.5)  # About to hit limit
    else:
        usage_score = int(SCORE_WEIGHTS["usage_ratio"] * 0.6)
    score += usage_score
    breakdown["usage_ratio"] = {"score": usage_score, "max": SCORE_WEIGHTS["usage_ratio"],
                                 "signal": f"{pct}% of plan used"}

    # Feature adoption — partial score for now
    feature_score = int(SCORE_WEIGHTS["feature_adoption"] * 0.5)
    score += feature_score
    breakdown["feature_adoption"] = {"score": feature_score, "max": SCORE_WEIGHTS["feature_adoption"]}

    # Pass rate trend — partial score
    trend_score = int(SCORE_WEIGHTS["pass_rate_trend"] * 0.6)
    score += trend_score
    breakdown["pass_rate_trend"] = {"score": trend_score, "max": SCORE_WEIGHTS["pass_rate_trend"]}

    # Deploy activity — partial score
    deploy_score = int(SCORE_WEIGHTS["deploy_activity"] * 0.5)
    score += deploy_score
    breakdown["deploy_activity"] = {"score": deploy_score, "max": SCORE_WEIGHTS["deploy_activity"]}

    # Login recency
    login_score = int(SCORE_WEIGHTS["login_recency"] * 0.7)
    score += login_score
    breakdown["login_recency"] = {"score": login_score, "max": SCORE_WEIGHTS["login_recency"]}

    risk = "churn_risk" if score < CHURN_THRESHOLD else ("expansion" if score > EXPAND_THRESHOLD else "healthy")

    return {
        "score": min(100, max(0, score)),
        "risk": risk,
        "breakdown": breakdown,
        "computed_at": datetime.now(timezone.utc).isoformat(),
    }


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _redis
    _redis = aioredis.from_url(REDIS_URL, encoding="utf-8", decode_responses=True)
    task = asyncio.create_task(event_consumer())
    logger.info("💚 Health Scoring Service ready")
    yield
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
    if _redis:
        await _redis.aclose()


APP_URL = os.getenv("APP_URL", "http://localhost:3000")
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

app = FastAPI(title="JarviisAI Health Scoring", version="1.0.0", lifespan=lifespan)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(CORSMiddleware, allow_origins=INTERNAL_ORIGINS, allow_credentials=True, allow_methods=["*"], allow_headers=["*"])


@app.get("/health")
async def health():
    return {"service": "health-scoring", "status": "ok"}

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



@app.get("/api/v1/health-score/{org_id}")
async def get_health_score(org_id: str):
    """Get health score for an org."""
    signals = {}
    usage = {}

    if _redis:
        raw = await _redis.hgetall(f"health:signals:{org_id}")
        signals = raw or {}

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"{USAGE_URL}/api/v1/usage/{org_id}")
            if resp.status_code == 200:
                usage = resp.json()
    except Exception:
        pass

    result = _compute_score(signals, usage)
    result["org_id"] = org_id
    return result


@app.get("/api/v1/health-score/admin/all")
async def get_all_health_scores(min_score: int = 0, max_score: int = 100, risk: Optional[str] = Query(None)):
    """Admin: get health scores for all orgs."""
    if not _redis:
        return {"scores": []}
    keys = await _redis.keys("health:signals:*")
    scores = []
    for key in keys[:50]:  # Cap at 50 for performance
        org_id = key.split(":")[-1]
        score_data = await get_health_score(org_id)
        if min_score <= score_data["score"] <= max_score:
            if risk is None or score_data["risk"] == risk:
                scores.append(score_data)
    scores.sort(key=lambda x: x["score"])
    return {"scores": scores, "total": len(scores)}
