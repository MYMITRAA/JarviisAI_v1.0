"""
Auth Service — Internal Endpoints.

Called by other JarviisAI services only (NOT exposed via API gateway).
Protected by X-Internal-Secret header.
"""

from fastapi import APIRouter, Depends, HTTPException, Header
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from typing import Optional
from datetime import datetime, timezone
import os
import logging

from app.core.database import get_db
from app.core.security import create_access_token, create_refresh_token
from app.models.user import User, Organization, OrganizationMember, OrgPlan
from app.services.auth_service import AuthService

logger = logging.getLogger("jarviis.auth.internal")
router = APIRouter(prefix="/internal", tags=["Internal"])

INTERNAL_SECRET = os.getenv("INTERNAL_SERVICE_SECRET", "jarviis-internal-secret")


def verify_internal(x_internal_secret: Optional[str] = Header(None)):
    if x_internal_secret != INTERNAL_SECRET:
        raise HTTPException(status_code=403, detail="Forbidden — internal endpoint")


# ── Billing plan update ───────────────────────────────────────

class PlanUpdateRequest(BaseModel):
    plan: str
    status: str = "active"
    stripe_customer_id: Optional[str] = None
    stripe_subscription_id: Optional[str] = None


@router.patch("/orgs/{org_id}/plan")
async def update_org_plan(
    org_id: str,
    data: PlanUpdateRequest,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(verify_internal),
):
    """Called by Billing service after Stripe webhook events."""
    org = await db.get(Organization, org_id)
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")

    # Map billing plan names to OrgPlan enum values
    plan_map = {
        "starter": OrgPlan.FREE,
        "free":    OrgPlan.FREE,
        "pro":     OrgPlan.PRO,
        "team":    OrgPlan.TEAM,
        "enterprise": OrgPlan.ENTERPRISE,
    }
    new_plan = plan_map.get(data.plan.lower(), OrgPlan.FREE)

    org.plan = new_plan
    if data.stripe_customer_id:
        org.stripe_customer_id = data.stripe_customer_id
    if data.stripe_subscription_id:
        org.stripe_subscription_id = data.stripe_subscription_id
    if data.status == "cancelled":
        org.plan = OrgPlan.FREE

    await db.flush()
    logger.info(f"Org {org_id} plan updated to {new_plan} (status: {data.status})")

    return {
        "org_id": org_id,
        "plan": new_plan,
        "status": data.status,
    }


# ── SSO user provisioning ─────────────────────────────────────

class SsoProvisionRequest(BaseModel):
    email: str
    given_name: Optional[str] = None
    family_name: Optional[str] = None
    org_slug: str
    provider: str = "saml"  # "saml" | "oidc"
    session_index: Optional[str] = None
    groups: Optional[list] = None
    picture_url: Optional[str] = None


@router.post("/sso/provision")
async def sso_provision_user(
    data: SsoProvisionRequest,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(verify_internal),
):
    """
    Called by SSO service after successful SAML/OIDC authentication.
    Creates or updates the user, ensures org membership, returns JWT tokens.
    """
    from app.core.security import create_access_token, create_refresh_token
    from app.core.config import settings

    # Find org by slug
    org = await db.scalar(select(Organization).where(Organization.slug == data.org_slug))
    if not org:
        raise HTTPException(status_code=404, detail=f"Organization '{data.org_slug}' not found")

    # Find or create user
    user = await db.scalar(select(User).where(User.email == data.email.lower()))
    now = datetime.now(timezone.utc)

    if not user:
        # Auto-provision new user
        full_name = " ".join(filter(None, [data.given_name, data.family_name])) or data.email.split("@")[0]
        import uuid
        user = User(
            id=str(uuid.uuid4()),
            email=data.email.lower(),
            full_name=full_name,
            hashed_password="",  # SSO users have no password
            is_email_verified=True,  # SSO provider handles email verification
            is_active=True,
            avatar_url=data.picture_url,
            sso_provider=data.provider,
            created_at=now,
        )
        db.add(user)
        await db.flush()
        logger.info(f"SSO auto-provisioned new user: {data.email} for org {data.org_slug}")
    else:
        # Update profile from SSO attributes
        if data.given_name or data.family_name:
            full_name = " ".join(filter(None, [data.given_name, data.family_name]))
            if full_name:
                user.full_name = full_name
        if data.picture_url and not user.avatar_url:
            user.avatar_url = data.picture_url
        user.last_login_at = now
        await db.flush()

    # Ensure org membership
    membership = await db.scalar(
        select(OrganizationMember).where(
            OrganizationMember.user_id == user.id,
            OrganizationMember.org_id == org.id,
        )
    )
    if not membership:
        membership = OrganizationMember(
            user_id=user.id,
            org_id=org.id,
            role="member",
            joined_at=now,
        )
        db.add(membership)
        await db.flush()
        logger.info(f"Added SSO user {data.email} to org {data.org_slug}")

    # Issue JWT tokens
    token_data = {
        "sub": user.id,
        "email": user.email,
        "org_id": str(org.id),
        "org_slug": org.slug,
        "role": membership.role,
        "plan": org.plan,
        "type": "access",
    }
    access_token = create_access_token(token_data)
    refresh_token = create_refresh_token({"sub": user.id, "type": "refresh"})

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "user": {
            "id": user.id,
            "email": user.email,
            "full_name": user.full_name,
            "avatar_url": user.avatar_url,
        },
        "org": {
            "id": str(org.id),
            "slug": org.slug,
            "name": org.name,
            "plan": org.plan,
        },
        "provisioned": membership is not None,
    }


# ── Trial expiry endpoints ────────────────────────────────────

@router.get("/orgs/expired-trials")
async def get_expired_trials(
    db: AsyncSession = Depends(get_db),
    _: None = Depends(verify_internal),
):
    """Called by trial worker every 15 minutes to find expired trials."""
    from datetime import datetime, timezone
    from sqlalchemy import select, and_
    from app.models.user import Organization

    now = datetime.now(timezone.utc)
    result = await db.execute(
        select(Organization).where(
            and_(
                Organization.trial_ends_at != None,
                Organization.trial_ends_at < now,
                Organization.trial_notified != True,  # Hasn't been notified yet
            )
        ).limit(50)
    )
    orgs = result.scalars().all()
    return {
        "orgs": [
            {
                "id": str(org.id),
                "slug": org.slug,
                "name": org.name,
                "trial_ends_at": org.trial_ends_at.isoformat() if org.trial_ends_at else None,
            }
            for org in orgs
        ]
    }


@router.post("/orgs/{org_id}/mark-trial-expired")
async def mark_trial_expired(
    org_id: str,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(verify_internal),
):
    """Mark trial as expired so worker doesn't fire the event again."""
    from app.models.user import Organization
    org = await db.get(Organization, org_id)
    if org:
        org.trial_notified = True
        await db.flush()
    return {"marked": True}
