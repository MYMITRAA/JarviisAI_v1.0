"""Redis client — used for token blacklisting, rate limiting, session caching."""

import redis.asyncio as aioredis
from app.core.config import settings
import logging

logger = logging.getLogger("jarviis.auth.redis")

redis_client: aioredis.Redis = aioredis.from_url(
    settings.REDIS_URL,
    encoding="utf-8",
    decode_responses=True,
    socket_connect_timeout=5,
    socket_timeout=5,
    retry_on_timeout=True,
    health_check_interval=30,
)


async def get_redis() -> aioredis.Redis:
    """FastAPI dependency — yields the shared Redis client."""
    yield redis_client
