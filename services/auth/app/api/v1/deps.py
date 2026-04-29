"""
FastAPI dependencies for authentication and authorization.
Used as Depends() throughout all protected endpoints.
"""

from fastapi import Depends, HTTPException, status, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from jose import JWTError

from app.core.database import get_db
from app.core.security import decode_token, is_token_blacklisted
from app.models.user import User, OrganizationMember, UserRole

security = HTTPBearer(auto_error=True)

CREDENTIALS_EXCEPTION = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Could not validate credentials",
    headers={"WWW-Authenticate": "Bearer"},
)


async def get_token_payload(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> dict:
    """Return the raw decoded JWT payload (for endpoints that need org context from token)."""
    try:
        payload = decode_token(credentials.credentials)
        return payload
    except JWTError:
        raise CREDENTIALS_EXCEPTION


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_db),
) -> User:
    """
    Validate JWT access token and return the authenticated user.
    Checks: valid JWT, not blacklisted, token type = access, user exists & active.
    """
    token = credentials.credentials

    try:
        payload = decode_token(token)
    except JWTError:
        raise CREDENTIALS_EXCEPTION

    # Verify token type
    if payload.get("type") != "access":
        raise CREDENTIALS_EXCEPTION

    # Check blacklist
    jti = payload.get("jti")
    if jti and await is_token_blacklisted(jti):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has been revoked. Please log in again.",
        )

    user_id = payload.get("sub")
    if not user_id:
        raise CREDENTIALS_EXCEPTION

    user = await db.get(User, user_id)
    if not user or not user.is_active:
        raise CREDENTIALS_EXCEPTION

    return user


async def get_current_verified_user(
    current_user: User = Depends(get_current_user),
) -> User:
    """Like get_current_user but also requires verified email."""
    if not current_user.is_email_verified:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Email verification required. Check your inbox.",
        )
    return current_user


def require_role(*roles: UserRole):
    """
    Dependency factory — require user to have one of the specified roles
    in the organization specified by org_id path param.

    Usage: Depends(require_role(UserRole.ADMIN, UserRole.OWNER))
    """
    async def _check(
        org_id: str,
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db),
    ) -> OrganizationMember:
        membership = await db.scalar(
            select(OrganizationMember).where(
                OrganizationMember.org_id == org_id,
                OrganizationMember.user_id == current_user.id,
                OrganizationMember.is_active == True,
            )
        )
        if not membership:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You are not a member of this organization",
            )
        if membership.role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"This action requires one of: {', '.join(r.value for r in roles)}",
            )
        return membership

    return _check


async def get_superadmin(current_user: User = Depends(get_current_user)) -> User:
    """Require superadmin — internal JarviisAI admin use only."""
    if not current_user.is_superadmin:
        raise HTTPException(status_code=403, detail="Superadmin access required")
    return current_user
