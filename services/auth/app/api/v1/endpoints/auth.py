"""Auth endpoints — register, login, OAuth, tokens, password management."""

from fastapi import APIRouter, Depends, Request, Response, status, BackgroundTasks
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession
from slowapi import Limiter
from slowapi.util import get_remote_address
import urllib.parse

from app.core.database import get_db
from app.core.security import decode_token, blacklist_token
from app.core.config import settings
from app.schemas.auth import (
    UserCreate, UserResponse, LoginRequest, TokenResponse,
    RefreshTokenRequest, LogoutRequest, MessageResponse,
    PasswordResetRequest, PasswordResetConfirm, EmailVerificationRequest,
    OnboardingCompleteRequest, OnboardingResponse,
)
from app.services.auth_service import AuthService
from app.services.org_service import OrgService
from app.services.email_service import email_service
from app.api.v1.deps import get_current_user
from app.models.user import User

router = APIRouter(prefix="/auth", tags=["Authentication"])
limiter = Limiter(key_func=get_remote_address)


def get_client_ip(request: Request) -> str:
    forwarded = request.headers.get("X-Forwarded-For")
    return forwarded.split(",")[0].strip() if forwarded else request.client.host


# ── Register ──────────────────────────────────────────────────

@router.post("/register", response_model=MessageResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit("10/minute")
async def register(
    request: Request,
    data: UserCreate,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    """Register with email/password. Sends verification email."""
    svc = AuthService(db)
    user = await svc.register(data, ip=get_client_ip(request))

    # Send verification email in background
    if user.email_verification_token:
        background_tasks.add_task(
            email_service.send_verification_email,
            user.email, user.email_verification_token, user.full_name
        )

    return {"message": "Account created. Check your email to verify your address."}


# ── Login ─────────────────────────────────────────────────────

@router.post("/login", response_model=TokenResponse)
@limiter.limit("20/minute")
async def login(
    request: Request,
    data: LoginRequest,
    db: AsyncSession = Depends(get_db),
):
    """Login with email/password. Returns JWT access + refresh tokens."""
    svc = AuthService(db)
    user, access_token, refresh_token = await svc.login(data, ip=get_client_ip(request))

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "expires_in": settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    }


# ── Token refresh ──────────────────────────────────────────────

@router.post("/refresh", response_model=TokenResponse)
@limiter.limit("30/minute")
async def refresh_token(
    request: Request,
    data: RefreshTokenRequest,
    db: AsyncSession = Depends(get_db),
):
    """Rotate refresh token — returns new access + refresh token pair."""
    svc = AuthService(db)
    access_token, refresh_token = await svc.refresh_tokens(data.refresh_token)

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "expires_in": settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    }


# ── Logout ────────────────────────────────────────────────────

@router.post("/logout", response_model=MessageResponse)
async def logout(
    data: LogoutRequest,
    current_user: User = Depends(get_current_user),
    request: Request = None,
    db: AsyncSession = Depends(get_db),
):
    """Logout — invalidates both access and refresh tokens."""
    # Get JTI from current access token
    auth_header = request.headers.get("Authorization", "")
    access_token = auth_header.replace("Bearer ", "")
    payload = decode_token(access_token)
    jti = payload.get("jti")
    exp = payload.get("exp")
    import time
    ttl = max(int(exp - time.time()), 1)

    svc = AuthService(db)
    await svc.logout(jti, data.refresh_token, ttl)

    return {"message": "Logged out successfully"}


# ── GitHub OAuth ──────────────────────────────────────────────

@router.get("/github")
async def github_login(request: Request):
    """Redirect to GitHub OAuth authorization page."""
    params = urllib.parse.urlencode({
        "client_id": settings.GITHUB_CLIENT_ID,
        "redirect_uri": settings.GITHUB_CALLBACK_URL,
        "scope": "read:user user:email",
        "state": "jarviis-oauth",  # In prod: generate CSRF token per request
    })
    return RedirectResponse(f"https://github.com/login/oauth/authorize?{params}")


@router.get("/github/callback")
async def github_callback(
    code: str,
    state: str = None,
    db: AsyncSession = Depends(get_db),
    request: Request = None,
):
    """GitHub OAuth callback — exchange code for tokens, redirect to frontend."""
    svc = AuthService(db)
    user, access_token, refresh_token, is_new = await svc.github_oauth_callback(
        code, ip=get_client_ip(request)
    )

    # Redirect to frontend with tokens
    redirect_url = f"{settings.FRONTEND_URL}/auth/callback"
    params = urllib.parse.urlencode({
        "access_token": access_token,
        "refresh_token": refresh_token,
        "is_new": "true" if is_new else "false",
    })
    return RedirectResponse(f"{redirect_url}?{params}")


# ── Email verification ────────────────────────────────────────

@router.post("/verify-email", response_model=MessageResponse)
async def verify_email(
    data: EmailVerificationRequest,
    db: AsyncSession = Depends(get_db),
):
    """Verify email address using token from verification email."""
    svc = AuthService(db)
    await svc.verify_email(data.token)
    return {"message": "Email verified successfully. You can now log in."}


@router.post("/resend-verification", response_model=MessageResponse)
@limiter.limit("3/hour")
async def resend_verification(
    request: Request,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Resend verification email for logged-in unverified user."""
    if current_user.is_email_verified:
        return {"message": "Email is already verified"}

    import secrets
    from datetime import datetime, timezone
    current_user.email_verification_token = secrets.token_urlsafe(32)
    current_user.email_verification_sent_at = datetime.now(timezone.utc)
    await db.flush()

    background_tasks.add_task(
        email_service.send_verification_email,
        current_user.email, current_user.email_verification_token, current_user.full_name
    )
    return {"message": "Verification email sent"}


# ── Password reset ────────────────────────────────────────────

@router.post("/password-reset/request", response_model=MessageResponse)
@limiter.limit("5/hour")
async def request_password_reset(
    request: Request,
    data: PasswordResetRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    """Request password reset email. Always returns success (no enumeration)."""
    svc = AuthService(db)
    user = await svc.request_password_reset(data.email)

    if user and user.password_reset_token:
        background_tasks.add_task(
            email_service.send_password_reset_email,
            user.email, user.password_reset_token
        )

    return {"message": "If an account with that email exists, a reset link has been sent."}


@router.post("/password-reset/confirm", response_model=MessageResponse)
@limiter.limit("10/hour")
async def confirm_password_reset(
    request: Request,
    data: PasswordResetConfirm,
    db: AsyncSession = Depends(get_db),
):
    """Complete password reset using token from email."""
    svc = AuthService(db)
    await svc.reset_password(data.token, data.new_password)
    return {"message": "Password reset successfully. You can now log in."}


# ── Onboarding ────────────────────────────────────────────────

@router.post("/onboarding/complete", response_model=OnboardingResponse)
async def complete_onboarding(
    data: OnboardingCompleteRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create first organization for a new user — final step of signup flow."""
    org_svc = OrgService(db)
    from app.schemas.auth import OrgCreate
    org = await org_svc.create_org(
        OrgCreate(name=data.org_name, slug=data.org_slug),
        owner_id=current_user.id,
    )

    auth_svc = AuthService(db)
    access_token, refresh_token = await auth_svc._issue_tokens(current_user)

    member_count = await org_svc.get_member_count(org.id)

    return {
        "user": current_user,
        "organization": {**org.__dict__, "member_count": member_count},
        "access_token": access_token,
        "refresh_token": refresh_token,
    }


@router.get("/beta/stats")
async def beta_stats(db: AsyncSession = Depends(get_db)):
    """Public endpoint - returns signup count for marketing page."""
    from sqlalchemy import select, func
    from app.models.user import Organization
    try:
        count = await db.scalar(select(func.count(Organization.id)))
        remaining = max(0, 500 - (count or 0))
        is_full = remaining == 0
        return {
            "total_orgs": count or 0,
            "beta_limit": 500,
            "remaining_spots": remaining,
            "beta_full": is_full,
        }
    except Exception:
        return {"total_orgs": 0, "beta_limit": 500, "remaining_spots": 500, "beta_full": False}
