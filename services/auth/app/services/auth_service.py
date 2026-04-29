"""
AuthService — all authentication business logic lives here.
Endpoints are thin; all logic is testable here.
"""

from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from fastapi import HTTPException, status
from passlib.context import CryptContext
import httpx
import secrets
import logging

from app.models.user import User, OAuthAccount, OAuthProvider, AuditLog
from app.schemas.auth import UserCreate, LoginRequest
from app.core.security import (
    create_access_token, create_refresh_token,
    decode_token, blacklist_token, store_refresh_token,
    revoke_all_user_tokens
)
from app.core.config import settings

logger = logging.getLogger("jarviis.auth.service")

# ── Password hashing ──────────────────────────────────────────
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


class AuthService:

    def __init__(self, db: AsyncSession):
        self.db = db

    # ── Registration ──────────────────────────────────────────

    async def register(self, data: UserCreate, ip: str = None) -> User:
        """Register a new user with email/password."""
        # Check existing
        existing = await self.db.scalar(
            select(User).where(User.email == data.email.lower())
        )
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="An account with this email already exists",
            )

        # Create user
        verification_token = secrets.token_urlsafe(32)
        user = User(
            email=data.email.lower(),
            full_name=data.full_name,
            hashed_password=hash_password(data.password),
            email_verification_token=verification_token,
            email_verification_sent_at=datetime.now(timezone.utc),
        )
        self.db.add(user)
        await self.db.flush()  # get the ID without committing

        await self._audit(user.id, None, "user.register", ip=ip)
        logger.info(f"New user registered: {user.email}")
        return user

    # ── Login ─────────────────────────────────────────────────

    async def login(
        self, data: LoginRequest, ip: str = None
    ) -> Tuple[User, str, str]:
        """Authenticate user, return (user, access_token, refresh_token)."""
        user = await self.db.scalar(
            select(User).where(User.email == data.email.lower())
        )

        # Generic error — don't reveal if email exists
        auth_error = HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

        if not user:
            raise auth_error

        # Check lockout
        if user.locked_until and user.locked_until > datetime.now(timezone.utc):
            remaining = int((user.locked_until - datetime.now(timezone.utc)).total_seconds() / 60)
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Account locked. Try again in {remaining} minutes.",
            )

        # Verify password
        if not user.hashed_password or not verify_password(data.password, user.hashed_password):
            # Increment failed attempts
            user.failed_login_attempts = (user.failed_login_attempts or 0) + 1
            if user.failed_login_attempts >= settings.MAX_LOGIN_ATTEMPTS:
                user.locked_until = datetime.now(timezone.utc) + timedelta(
                    minutes=settings.LOCKOUT_DURATION_MINUTES
                )
                logger.warning(f"Account locked after {user.failed_login_attempts} attempts: {user.email}")
            await self.db.flush()
            raise auth_error

        if not user.is_active:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account is deactivated")

        # Success — reset counters
        user.failed_login_attempts = 0
        user.locked_until = None
        user.last_login_at = datetime.now(timezone.utc)
        user.last_login_ip = ip
        await self.db.flush()

        access_token, refresh_token = await self._issue_tokens(user)
        await self._audit(user.id, None, "user.login", ip=ip)
        return user, access_token, refresh_token

    # ── Token refresh ──────────────────────────────────────────

    async def refresh_tokens(self, refresh_token: str) -> Tuple[str, str]:
        """Rotate refresh token — old token invalidated, new pair issued."""
        from jose import JWTError
        try:
            payload = decode_token(refresh_token)
        except JWTError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired refresh token",
            )

        if payload.get("type") != "refresh":
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token type")

        user_id = payload["sub"]
        jti = payload["jti"]

        # Blacklist old refresh token
        from datetime import timezone as tz
        exp = payload["exp"]
        now = int(datetime.now(timezone.utc).timestamp())
        ttl = max(exp - now, 1)
        await blacklist_token(jti, ttl)

        user = await self.db.get(User, user_id)
        if not user or not user.is_active:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")

        return await self._issue_tokens(user)

    # ── Logout ────────────────────────────────────────────────

    async def logout(self, access_token_jti: str, refresh_token: str, access_ttl: int) -> None:
        """Blacklist both access and refresh tokens."""
        await blacklist_token(access_token_jti, access_ttl)
        try:
            payload = decode_token(refresh_token)
            exp = payload["exp"]
            now = int(datetime.now(timezone.utc).timestamp())
            ttl = max(exp - now, 1)
            await blacklist_token(payload["jti"], ttl)
        except Exception:
            pass  # refresh token already expired — that's fine

    # ── Email verification ────────────────────────────────────

    async def verify_email(self, token: str) -> User:
        """Verify email address from token."""
        user = await self.db.scalar(
            select(User).where(User.email_verification_token == token)
        )
        if not user:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid verification token")

        # Check expiry (24h)
        if user.email_verification_sent_at:
            age = datetime.now(timezone.utc) - user.email_verification_sent_at
            if age.total_seconds() > settings.EMAIL_VERIFICATION_TOKEN_EXPIRE_HOURS * 3600:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Verification token expired")

        user.is_email_verified = True
        user.email_verification_token = None
        await self.db.flush()
        return user

    # ── Password reset ────────────────────────────────────────

    async def request_password_reset(self, email: str) -> Optional[User]:
        """Generate password reset token. Always returns success to prevent enumeration."""
        user = await self.db.scalar(select(User).where(User.email == email.lower()))
        if not user:
            return None  # Don't reveal user doesn't exist

        token = secrets.token_urlsafe(32)
        user.password_reset_token = token
        user.password_reset_expires_at = datetime.now(timezone.utc) + timedelta(
            hours=settings.PASSWORD_RESET_TOKEN_EXPIRE_HOURS
        )
        await self.db.flush()
        return user

    async def reset_password(self, token: str, new_password: str) -> User:
        """Reset password using token."""
        user = await self.db.scalar(
            select(User).where(User.password_reset_token == token)
        )
        if not user:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or expired reset token")

        if not user.password_reset_expires_at or user.password_reset_expires_at < datetime.now(timezone.utc):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Reset token has expired")

        user.hashed_password = hash_password(new_password)
        user.password_reset_token = None
        user.password_reset_expires_at = None
        await self.db.flush()

        # Revoke all existing tokens
        await revoke_all_user_tokens(user.id)
        return user

    # ── GitHub OAuth ──────────────────────────────────────────

    async def github_oauth_callback(
        self, code: str, ip: str = None
    ) -> Tuple[User, str, str, bool]:
        """
        Exchange GitHub code for user data, create/update user.
        Returns (user, access_token, refresh_token, is_new_user)
        """
        # Exchange code for token
        async with httpx.AsyncClient() as client:
            token_resp = await client.post(
                "https://github.com/login/oauth/access_token",
                data={
                    "client_id": settings.GITHUB_CLIENT_ID,
                    "client_secret": settings.GITHUB_CLIENT_SECRET,
                    "code": code,
                },
                headers={"Accept": "application/json"},
            )
            token_data = token_resp.json()

        if "error" in token_data:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"GitHub OAuth error: {token_data['error']}")

        github_token = token_data["access_token"]

        # Get GitHub user data
        async with httpx.AsyncClient() as client:
            user_resp = await client.get(
                "https://api.github.com/user",
                headers={"Authorization": f"Bearer {github_token}"},
            )
            emails_resp = await client.get(
                "https://api.github.com/user/emails",
                headers={"Authorization": f"Bearer {github_token}"},
            )

        gh_user = user_resp.json()
        gh_emails = emails_resp.json()

        # Get primary verified email
        primary_email = None
        for e in gh_emails:
            if e.get("primary") and e.get("verified"):
                primary_email = e["email"]
                break
        if not primary_email and gh_emails:
            primary_email = gh_emails[0]["email"]

        if not primary_email:
            raise HTTPException(status_code=400, detail="Could not get email from GitHub account")

        return await self._oauth_get_or_create(
            provider=OAuthProvider.GITHUB,
            provider_user_id=str(gh_user["id"]),
            email=primary_email,
            full_name=gh_user.get("name") or gh_user.get("login"),
            avatar_url=gh_user.get("avatar_url"),
            provider_username=gh_user.get("login"),
            access_token=github_token,
            raw_data=gh_user,
            ip=ip,
        )

    # ── Helpers ───────────────────────────────────────────────

    async def _issue_tokens(self, user: User) -> Tuple[str, str]:
        """Issue access + refresh token pair with full org context."""
        from app.models.user import OrganizationMember, Organization
        membership = await self.db.scalar(
            select(OrganizationMember).where(
                OrganizationMember.user_id == user.id,
                OrganizationMember.is_active == True
            ).limit(1)
        )

        # Fetch org details for slug + plan
        org = None
        if membership:
            org = await self.db.get(Organization, membership.org_id)

        access = create_access_token(
            subject=user.id,
            org_id=str(org.id) if org else None,
            role=membership.role if membership else None,
            extra_data={
                "email": user.email,
                "org_slug": org.slug if org else None,
                "org_name": org.name if org else None,
                "plan": org.effective_plan if org else "free",
                "trial_active": org.trial_active if org else False,
                "trial_hours_remaining": org.trial_hours_remaining if org else 0,
                "type": "access",
            },
        )
        refresh = create_refresh_token(subject=user.id)

        refresh_payload = decode_token(refresh)
        await store_refresh_token(user.id, refresh_payload["jti"], refresh)

        return access, refresh

    async def _oauth_get_or_create(
        self, provider, provider_user_id, email,
        full_name=None, avatar_url=None, provider_username=None,
        access_token=None, raw_data=None, ip=None
    ) -> Tuple[User, str, str, bool]:
        """Find or create user for OAuth login."""
        # Check existing OAuth account
        oauth = await self.db.scalar(
            select(OAuthAccount).where(
                OAuthAccount.provider == provider,
                OAuthAccount.provider_user_id == provider_user_id,
            )
        )

        is_new = False
        if oauth:
            user = await self.db.get(User, oauth.user_id)
            # Update OAuth token
            oauth.access_token = access_token
            oauth.raw_data = raw_data
        else:
            # Try to find user by email
            user = await self.db.scalar(select(User).where(User.email == email.lower()))
            if not user:
                user = User(
                    email=email.lower(),
                    full_name=full_name,
                    avatar_url=avatar_url,
                    is_email_verified=True,  # OAuth = verified
                )
                self.db.add(user)
                await self.db.flush()
                is_new = True

            oauth = OAuthAccount(
                user_id=user.id,
                provider=provider,
                provider_user_id=provider_user_id,
                provider_email=email,
                provider_username=provider_username,
                access_token=access_token,
                raw_data=raw_data,
            )
            self.db.add(oauth)
            await self.db.flush()

        user.last_login_at = datetime.now(timezone.utc)
        user.last_login_ip = ip
        if not user.avatar_url and avatar_url:
            user.avatar_url = avatar_url

        access, refresh = await self._issue_tokens(user)
        await self._audit(user.id, None, "user.oauth_login", ip=ip, metadata={"provider": str(provider)})
        return user, access, refresh, is_new

    async def _audit(
        self, user_id: str, org_id: Optional[str], action: str,
        ip: str = None, resource_type: str = None,
        resource_id: str = None, metadata: dict = None
    ):
        """Write an audit log entry."""
        log = AuditLog(
            user_id=user_id,
            org_id=org_id,
            action=action,
            ip_address=ip,
            resource_type=resource_type,
            resource_id=resource_id,
            metadata=metadata,
        )
        self.db.add(log)
