"""User profile endpoints."""

from fastapi import APIRouter, Depends, status, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.database import get_db
from app.schemas.auth import UserResponse, UserUpdateRequest, MessageResponse, PasswordChangeRequest
from app.services.auth_service import AuthService, hash_password, verify_password
from app.api.v1.deps import get_current_user, get_token_payload
from app.models.user import User, Organization, OrganizationMember
from fastapi import HTTPException

router = APIRouter(prefix="/users", tags=["Users"])


@router.get("/me", response_model=UserResponse)
async def get_me(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get current authenticated user's profile including org context."""
    # Get org membership to include org context in response
    membership = await db.scalar(
        select(OrganizationMember).where(
            OrganizationMember.user_id == current_user.id,
            OrganizationMember.is_active == True,
        ).limit(1)
    )

    org = None
    if membership:
        org = await db.get(Organization, membership.org_id)

    # Build response with org context + trial info
    from datetime import datetime, timezone
    trial_active = False
    trial_hours_remaining = 0.0
    if org and org.trial_ends_at:
        now = datetime.now(timezone.utc)
        trial_ends = org.trial_ends_at
        if not trial_ends.tzinfo:
            trial_ends = trial_ends.replace(tzinfo=timezone.utc)
        if trial_ends > now:
            trial_active = True
            trial_hours_remaining = round((trial_ends - now).total_seconds() / 3600, 1)

    return {
        "id": current_user.id,
        "email": current_user.email,
        "full_name": current_user.full_name,
        "avatar_url": current_user.avatar_url,
        "is_email_verified": current_user.is_email_verified,
        "is_active": current_user.is_active,
        "created_at": current_user.created_at,
        "last_login_at": current_user.last_login_at,
        "sso_provider": getattr(current_user, "sso_provider", None),
        # Org context
        "org_id": str(org.id) if org else None,
        "org_slug": org.slug if org else None,
        "org_name": org.name if org else None,
        "role": membership.role if membership else None,
        "plan": str(org.plan) if org else "free",
        # Trial
        "trial_active": trial_active,
        "trial_hours_remaining": trial_hours_remaining,
        # Superadmin
        "is_superadmin": getattr(current_user, "is_superadmin", False),
    }


@router.patch("/me", response_model=UserResponse)
async def update_me(
    data: UserUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if data.full_name is not None:
        current_user.full_name = data.full_name
    if data.avatar_url is not None:
        current_user.avatar_url = data.avatar_url
    await db.flush()
    return current_user


@router.post("/me/change-password", response_model=MessageResponse)
async def change_password(
    data: PasswordChangeRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Change password for authenticated user."""
    if not current_user.hashed_password:
        raise HTTPException(400, "Account uses OAuth — set a password first via password reset")

    if not verify_password(data.current_password, current_user.hashed_password):
        raise HTTPException(400, "Current password is incorrect")

    current_user.hashed_password = hash_password(data.new_password)
    await db.flush()

    from app.core.security import revoke_all_user_tokens
    await revoke_all_user_tokens(current_user.id)

    return {"message": "Password changed successfully. Please log in again."}


@router.delete("/me", response_model=MessageResponse)
async def delete_account(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Soft-delete current user's account."""
    current_user.is_active = False
    current_user.email = f"deleted_{current_user.id}@deleted.jarviis"
    await db.flush()

    from app.core.security import revoke_all_user_tokens
    await revoke_all_user_tokens(current_user.id)

    return {"message": "Account deleted successfully"}
