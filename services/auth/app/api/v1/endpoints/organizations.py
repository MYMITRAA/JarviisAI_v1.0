"""Organization management endpoints."""

from fastapi import APIRouter, Depends, status, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.schemas.auth import (
    OrgCreate, OrgUpdate, OrgResponse, MemberResponse,
    MemberUpdateRequest, InviteMemberRequest, InviteResponse, MessageResponse,
)
from app.services.org_service import OrgService
from app.services.email_service import email_service
from app.api.v1.deps import get_current_user, require_role
from app.models.user import User, UserRole

router = APIRouter(prefix="/organizations", tags=["Organizations"])


@router.post("", response_model=OrgResponse, status_code=status.HTTP_201_CREATED)
async def create_organization(
    data: OrgCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a new organization. Caller becomes the owner."""
    svc = OrgService(db)
    org = await svc.create_org(data, owner_id=current_user.id)
    member_count = await svc.get_member_count(org.id)
    return {**org.__dict__, "member_count": member_count}


@router.get("/{org_slug}", response_model=OrgResponse)
async def get_organization(
    org_slug: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from fastapi import HTTPException
    svc = OrgService(db)
    org = await svc.get_org_by_slug(org_slug)
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")
    member_count = await svc.get_member_count(org.id)
    return {**org.__dict__, "member_count": member_count}


@router.patch("/{org_id}", response_model=OrgResponse)
async def update_organization(
    org_id: str,
    data: OrgUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update organization details. Requires Admin or Owner role."""
    svc = OrgService(db)
    org = await svc.update_org(org_id, data, current_user.id)
    member_count = await svc.get_member_count(org.id)
    return {**org.__dict__, "member_count": member_count}


# ── Members ────────────────────────────────────────────────────

@router.get("/{org_id}/members", response_model=list[MemberResponse])
async def list_members(
    org_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    svc = OrgService(db)
    return await svc.get_members(org_id)


@router.patch("/{org_id}/members/{member_id}", response_model=MessageResponse)
async def update_member_role(
    org_id: str,
    member_id: str,
    data: MemberUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    svc = OrgService(db)
    await svc.update_member_role(org_id, member_id, data.role, current_user.id)
    return {"message": "Member role updated"}


@router.delete("/{org_id}/members/{member_id}", response_model=MessageResponse)
async def remove_member(
    org_id: str,
    member_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    svc = OrgService(db)
    await svc.remove_member(org_id, member_id, current_user.id)
    return {"message": "Member removed"}


# ── Invites ────────────────────────────────────────────────────

@router.post("/{org_id}/invites", response_model=InviteResponse, status_code=201)
async def invite_member(
    org_id: str,
    data: InviteMemberRequest,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Send an invite email to a new member."""
    svc = OrgService(db)
    invite = await svc.invite_member(org_id, data, inviter_id=current_user.id)
    org = await svc.get_org(org_id)

    background_tasks.add_task(
        email_service.send_invite_email,
        invite.email,
        current_user.full_name or current_user.email,
        org.name,
        invite.token,
        invite.role,
    )
    return invite


@router.post("/invites/{token}/accept", response_model=MessageResponse)
async def accept_invite(
    token: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    svc = OrgService(db)
    await svc.accept_invite(token, current_user.id)
    return {"message": "Successfully joined the organization"}


@router.get("", response_model=list)
async def list_all_organizations(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    search: Optional[str] = Query(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Superadmin: list all organizations. Requires is_superadmin flag."""
    if not getattr(current_user, "is_superadmin", False):
        raise HTTPException(status_code=403, detail="Superadmin access required")
    
    from sqlalchemy import select, or_
    from app.models.user import Organization
    
    q = select(Organization).where(Organization.is_active == True)
    if search:
        q = q.where(or_(
            Organization.name.ilike(f"%{search}%"),
            Organization.slug.ilike(f"%{search}%"),
        ))
    q = q.offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(q)
    orgs = result.scalars().all()
    
    return [
        {
            "id": str(o.id),
            "name": o.name,
            "slug": o.slug,
            "plan": str(o.plan),
            "created_at": o.created_at.isoformat() if o.created_at else None,
        }
        for o in orgs
    ]
