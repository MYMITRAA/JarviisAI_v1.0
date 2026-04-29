"""OrgService — organization and membership management."""

from datetime import datetime, timedelta, timezone
from typing import List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from fastapi import HTTPException, status
import secrets
import logging

from app.models.user import (
    Organization, OrganizationMember, OrganizationInvite,
    User, UserRole, OrgPlan, InviteStatus, AuditLog
)
from app.schemas.auth import OrgCreate, OrgUpdate, InviteMemberRequest

logger = logging.getLogger("jarviis.auth.org")

# Plan limits
PLAN_LIMITS = {
    OrgPlan.FREE:       {"test_runs": 200,     "members": 1},
    OrgPlan.STARTER:    {"test_runs": 2_000,   "members": 3},
    OrgPlan.GROWTH:     {"test_runs": 20_000,  "members": 10},
    OrgPlan.BUSINESS:   {"test_runs": 200_000, "members": 50},
    OrgPlan.ENTERPRISE: {"test_runs": 999_999, "members": 999},
}


class OrgService:

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_org(self, data: OrgCreate, owner_id: str) -> Organization:
        """Create a new organization with a 2-day Pro trial and fire trial.started event."""
        # Check slug availability
        existing = await self.db.scalar(
            select(Organization).where(Organization.slug == data.slug)
        )
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Organization slug is already taken",
            )

        now = datetime.now(timezone.utc)
        # 2-day trial — Pro features for 48 hours
        trial_ends = now + timedelta(days=2)

        # Create org on Free plan with trial overlay
        org = Organization(
            name=data.name,
            slug=data.slug,
            description=data.description,
            plan=OrgPlan.FREE,
            trial_ends_at=trial_ends,
            monthly_test_run_limit=PLAN_LIMITS[OrgPlan.FREE]["test_runs"],
            usage_reset_at=now + timedelta(days=30),
        )
        self.db.add(org)
        await self.db.flush()

        # Add owner membership
        membership = OrganizationMember(
            org_id=org.id,
            user_id=owner_id,
            role=UserRole.OWNER,
        )
        self.db.add(membership)
        await self.db.flush()

        # Fire billing.trial_started event
        try:
            import httpx as _httpx
            import os
            events_url = os.getenv("EVENTS_SERVICE_URL", "http://events:8017")
            async with _httpx.AsyncClient(timeout=2.0) as client:
                await client.post(f"{events_url}/api/v1/events/publish", json={
                    "event": "billing.trial_started",
                    "org_id": str(org.id),
                    "actor_id": owner_id,
                    "source_service": "auth",
                    "payload": {
                        "org_slug": org.slug,
                        "trial_ends_at": trial_ends.isoformat(),
                        "trial_days": 2,
                        "trial_plan": "pro",
                    },
                })
        except Exception:
            pass

        logger.info(f"Organization created: {org.slug} (2-day trial until {trial_ends.isoformat()})")
        return org

    async def get_org(self, org_id: str) -> Optional[Organization]:
        return await self.db.get(Organization, org_id)

    async def get_org_by_slug(self, slug: str) -> Optional[Organization]:
        return await self.db.scalar(
            select(Organization).where(Organization.slug == slug)
        )

    async def update_org(self, org_id: str, data: OrgUpdate, requester_id: str) -> Organization:
        org = await self.get_org(org_id)
        if not org:
            raise HTTPException(status_code=404, detail="Organization not found")

        if data.name is not None:
            org.name = data.name
        if data.description is not None:
            org.description = data.description
        if data.logo_url is not None:
            org.logo_url = data.logo_url

        await self.db.flush()
        return org

    async def get_members(self, org_id: str) -> List[dict]:
        """Get all active members with user details."""
        result = await self.db.execute(
            select(OrganizationMember, User)
            .join(User, OrganizationMember.user_id == User.id)
            .where(
                OrganizationMember.org_id == org_id,
                OrganizationMember.is_active == True
            )
            .order_by(OrganizationMember.joined_at)
        )
        rows = result.all()

        members = []
        for membership, user in rows:
            members.append({
                "id": membership.id,
                "user_id": user.id,
                "email": user.email,
                "full_name": user.full_name,
                "avatar_url": user.avatar_url,
                "role": membership.role,
                "joined_at": membership.joined_at,
            })
        return members

    async def get_member_count(self, org_id: str) -> int:
        return await self.db.scalar(
            select(func.count(OrganizationMember.id)).where(
                OrganizationMember.org_id == org_id,
                OrganizationMember.is_active == True
            )
        ) or 0

    async def update_member_role(
        self, org_id: str, member_id: str, new_role: UserRole, requester_id: str
    ) -> OrganizationMember:
        membership = await self.db.scalar(
            select(OrganizationMember).where(
                OrganizationMember.id == member_id,
                OrganizationMember.org_id == org_id,
            )
        )
        if not membership:
            raise HTTPException(status_code=404, detail="Member not found")
        if membership.role == UserRole.OWNER:
            raise HTTPException(status_code=400, detail="Cannot change organization owner's role")

        membership.role = new_role
        await self.db.flush()
        return membership

    async def remove_member(self, org_id: str, member_id: str, requester_id: str) -> None:
        membership = await self.db.scalar(
            select(OrganizationMember).where(
                OrganizationMember.id == member_id,
                OrganizationMember.org_id == org_id,
            )
        )
        if not membership:
            raise HTTPException(status_code=404, detail="Member not found")
        if membership.role == UserRole.OWNER:
            raise HTTPException(status_code=400, detail="Cannot remove organization owner")
        if membership.user_id == requester_id:
            raise HTTPException(status_code=400, detail="Cannot remove yourself — transfer ownership first")

        membership.is_active = False
        await self.db.flush()

    async def invite_member(
        self, org_id: str, data: InviteMemberRequest, inviter_id: str
    ) -> OrganizationInvite:
        """Create an invite token and return it (email sending handled by caller)."""
        org = await self.get_org(org_id)
        if not org:
            raise HTTPException(status_code=404, detail="Organization not found")

        # Check member limit
        count = await self.get_member_count(org_id)
        limit = PLAN_LIMITS.get(org.plan, {}).get("members", 1)
        if count >= limit:
            raise HTTPException(
                status_code=status.HTTP_402_PAYMENT_REQUIRED,
                detail=f"Member limit reached for {org.plan} plan. Upgrade to add more members.",
            )

        # Check for existing active invite
        existing = await self.db.scalar(
            select(OrganizationInvite).where(
                OrganizationInvite.org_id == org_id,
                OrganizationInvite.email == data.email.lower(),
                OrganizationInvite.status == InviteStatus.PENDING,
            )
        )
        if existing:
            raise HTTPException(status_code=409, detail="An active invite already exists for this email")

        invite = OrganizationInvite(
            org_id=org_id,
            invited_by_id=inviter_id,
            email=data.email.lower(),
            role=data.role,
            token=secrets.token_urlsafe(32),
            expires_at=datetime.now(timezone.utc) + timedelta(days=7),
        )
        self.db.add(invite)
        await self.db.flush()
        return invite

    async def accept_invite(self, token: str, user_id: str) -> OrganizationMember:
        """Accept an invite and add user to org."""
        invite = await self.db.scalar(
            select(OrganizationInvite).where(OrganizationInvite.token == token)
        )
        if not invite or invite.status != InviteStatus.PENDING:
            raise HTTPException(status_code=400, detail="Invalid or expired invite")

        if invite.expires_at < datetime.now(timezone.utc):
            invite.status = InviteStatus.EXPIRED
            raise HTTPException(status_code=400, detail="Invite has expired")

        # Check if already a member
        existing = await self.db.scalar(
            select(OrganizationMember).where(
                OrganizationMember.org_id == invite.org_id,
                OrganizationMember.user_id == user_id,
            )
        )
        if existing:
            raise HTTPException(status_code=409, detail="You are already a member of this organization")

        membership = OrganizationMember(
            org_id=invite.org_id,
            user_id=user_id,
            role=invite.role,
            invited_by_id=invite.invited_by_id,
        )
        self.db.add(membership)

        invite.status = InviteStatus.ACCEPTED
        invite.accepted_at = datetime.now(timezone.utc)
        await self.db.flush()
        return membership
