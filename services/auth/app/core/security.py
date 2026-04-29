"""
JWT token management.
- Access tokens: 15 min, used for API auth
- Refresh tokens: 7 days, stored in Redis, rotated on use
- Blacklisting: revoked tokens stored in Redis until expiry
"""

from datetime import datetime, timedelta, timezone
from typing import Optional
from jose import JWTError, jwt
from app.core.config import settings
from app.core.redis import redis_client
import uuid
import logging

logger = logging.getLogger("jarviis.auth.security")

BLACKLIST_PREFIX = "blacklist:token:"
REFRESH_PREFIX = "refresh:token:"


def create_access_token(
    subject: str,
    org_id: Optional[str] = None,
    role: Optional[str] = None,
    extra_data: Optional[dict] = None,
) -> str:
    """Create a short-lived JWT access token."""
    now = datetime.now(timezone.utc)
    expire = now + timedelta(minutes=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES)

    payload = {
        "sub": str(subject),          # user ID
        "iat": now,
        "exp": expire,
        "jti": str(uuid.uuid4()),     # unique token ID for blacklisting
        "type": "access",
        "org_id": org_id,
        "role": role,
    }
    if extra_data:
        payload.update(extra_data)

    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def create_refresh_token(subject: str) -> str:
    """Create a long-lived refresh token and store its ID in Redis."""
    now = datetime.now(timezone.utc)
    expire = now + timedelta(days=settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS)
    jti = str(uuid.uuid4())

    payload = {
        "sub": str(subject),
        "iat": now,
        "exp": expire,
        "jti": jti,
        "type": "refresh",
    }

    token = jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)
    return token


def decode_token(token: str) -> dict:
    """Decode and validate a JWT token. Raises JWTError on failure."""
    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET,
            algorithms=[settings.JWT_ALGORITHM],
        )
        return payload
    except JWTError as e:
        logger.warning(f"Token decode failed: {e}")
        raise


async def blacklist_token(jti: str, expire_seconds: int) -> None:
    """Add a token JTI to the Redis blacklist."""
    key = f"{BLACKLIST_PREFIX}{jti}"
    await redis_client.setex(key, expire_seconds, "1")


async def is_token_blacklisted(jti: str) -> bool:
    """Check if a token has been blacklisted."""
    key = f"{BLACKLIST_PREFIX}{jti}"
    return bool(await redis_client.exists(key))


async def store_refresh_token(user_id: str, jti: str, token: str) -> None:
    """Store refresh token in Redis for rotation tracking."""
    key = f"{REFRESH_PREFIX}{user_id}:{jti}"
    expire = settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS * 86400
    await redis_client.setex(key, expire, token)


async def revoke_all_user_tokens(user_id: str) -> None:
    """Revoke all refresh tokens for a user (e.g., on password change)."""
    pattern = f"{REFRESH_PREFIX}{user_id}:*"
    keys = await redis_client.keys(pattern)
    if keys:
        await redis_client.delete(*keys)
        logger.info(f"Revoked {len(keys)} tokens for user {user_id}")
