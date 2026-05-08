"""
SQLAlchemy ORM models.
All tables scoped to organization_id for multi-tenancy.
UUIDs everywhere — no sequential IDs exposed to clients.
"""

import uuid
from datetime import datetime, timezone
from typing import Optional, List
from sqlalchemy import (
    String, Boolean, DateTime, ForeignKey, Text,
    UniqueConstraint, Index, Enum as SAEnum, Integer
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy import JSON
from app.core.database import Base
import enum
from sqlalchemy import String

def utcnow():
    return datetime.now(timezone.utc)


def new_uuid():
    return str(uuid.uuid4())


# ── Enums ─────────────────────────────────────────────────────

class UserRole(str, enum.Enum):
    OWNER   = "owner"    # full control, billing access
    ADMIN   = "admin"    # manage members, projects
    MEMBER  = "member"   # create/run tests, view results
    VIEWER  = "viewer"   # read-only access

class OrgPlan(str, enum.Enum):
    FREE       = "free"
    STARTER    = "starter"
    GROWTH     = "growth"
    BUSINESS   = "business"
    ENTERPRISE = "enterprise"

class OAuthProvider(str, enum.Enum):
    GITHUB = "github"
    GOOGLE = "google"

class InviteStatus(str, enum.Enum):
    PENDING  = "pending"
    ACCEPTED = "accepted"
    EXPIRED  = "expired"
    REVOKED  = "revoked"


# ── Users ─────────────────────────────────────────────────────

class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=new_uuid
    )
    email: Mapped[str] = mapped_column(
        String(255), unique=True, nullable=False, index=True
    )
    full_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    avatar_url: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    hashed_password: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    # Email verification
    is_email_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    email_verification_token: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    email_verification_sent_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Password reset
    password_reset_token: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    password_reset_expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Security
    failed_login_attempts: Mapped[int] = mapped_column(Integer, default=0)
    locked_until: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    last_login_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    last_login_ip: Mapped[Optional[str]] = mapped_column(String(45), nullable=True)

    # Status
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_superadmin: Mapped[bool] = mapped_column(Boolean, default=False)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    # Relationships
    oauth_accounts: Mapped[List["OAuthAccount"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    org_memberships: Mapped[List["OrganizationMember"]] = relationship(back_populates="user", cascade="all, delete-orphan", foreign_keys="[OrganizationMember.user_id]")


    def __repr__(self):
        return f"<User {self.email}>"


# ── OAuth Accounts ────────────────────────────────────────────

class OAuthAccount(Base):
    __tablename__ = "oauth_accounts"
    __table_args__ = (
        UniqueConstraint("provider", "provider_user_id", name="uq_oauth_provider_user"),
    )

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=new_uuid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    provider: Mapped[str] = mapped_column(SAEnum(OAuthProvider), nullable=False)
    provider_user_id: Mapped[str] = mapped_column(String(255), nullable=False)
    provider_email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    provider_username: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    access_token: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    refresh_token: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    token_expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    raw_data: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    user: Mapped["User"] = relationship(back_populates="oauth_accounts")


# ── Organizations ─────────────────────────────────────────────

class Organization(Base):
    __tablename__ = "organizations"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=new_uuid)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    logo_url: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)

    # Plan & billing
    plan: Mapped[str] = mapped_column(SAEnum(OrgPlan), default=OrgPlan.FREE, nullable=False)
    stripe_customer_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    stripe_subscription_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    trial_ends_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    trial_notified: Mapped[bool] = mapped_column(Boolean, default=False)

    # Usage limits (enforced at API layer)
    monthly_test_run_limit: Mapped[int] = mapped_column(Integer, default=200)
    monthly_test_runs_used: Mapped[int] = mapped_column(Integer, default=0)
    usage_reset_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # SSO (enterprise)
    sso_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    sso_provider: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    saml_metadata_url: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)

    # Settings
    settings: Mapped[Optional[dict]] = mapped_column(JSON, default={})

    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    # Relationships
    members: Mapped[List["OrganizationMember"]] = relationship(back_populates="organization", cascade="all, delete-orphan")
    invites: Mapped[List["OrganizationInvite"]] = relationship(back_populates="organization", cascade="all, delete-orphan")

    @property
    def effective_plan(self) -> str:
        """
        Returns the org's effective plan, accounting for active trial.
        During trial: returns 'pro' (trial gives Pro features)
        After trial: returns actual plan
        """
        if self.trial_ends_at and self.trial_ends_at > datetime.now(timezone.utc):
            return "pro"  # Trial gives Pro features
        return str(self.plan)

    @property
    def trial_active(self) -> bool:
        return bool(self.trial_ends_at and self.trial_ends_at > datetime.now(timezone.utc))

    @property
    def trial_hours_remaining(self) -> float:
        if not self.trial_active:
            return 0
        delta = self.trial_ends_at - datetime.now(timezone.utc)
        return round(delta.total_seconds() / 3600, 1)


# ── Organization Members ──────────────────────────────────────

class OrganizationMember(Base):
    __tablename__ = "organization_members"
    __table_args__ = (
        UniqueConstraint("org_id", "user_id", name="uq_org_member"),
        Index("ix_org_members_org_id", "org_id"),
        Index("ix_org_members_user_id", "user_id"),
    )

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=new_uuid)
    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    role: Mapped[str] = mapped_column(SAEnum(UserRole), default=UserRole.MEMBER, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    joined_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    invited_by_id: Mapped[Optional[str]] = mapped_column(ForeignKey("users.id"), nullable=True)

    user: Mapped["User"] = relationship(back_populates="org_memberships", foreign_keys=[user_id])
    invited_by: Mapped[Optional["User"]] = relationship(
    "User",
    foreign_keys=[invited_by_id]
    )
    organization: Mapped["Organization"] = relationship(back_populates="members")


# ── Organization Invites ──────────────────────────────────────

class OrganizationInvite(Base):
    __tablename__ = "organization_invites"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=new_uuid)
    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    invited_by_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(SAEnum(UserRole), default=UserRole.MEMBER)
    token: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    status: Mapped[str] = mapped_column(String(50), default=InviteStatus.PENDING.value) 
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    accepted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    organization: Mapped["Organization"] = relationship(back_populates="invites")


# ── Audit Log ─────────────────────────────────────────────────

class AuditLog(Base):
    __tablename__ = "audit_logs"
    __table_args__ = (
        Index("ix_audit_logs_org_id_created", "org_id", "created_at"),
        Index("ix_audit_logs_user_id", "user_id"),
    )

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=new_uuid)
    org_id: Mapped[Optional[str]] = mapped_column(ForeignKey("organizations.id", ondelete="SET NULL"), nullable=True)
    user_id: Mapped[Optional[str]] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    action: Mapped[str] = mapped_column(String(100), nullable=False)  # e.g., "user.login", "org.member.invite"
    resource_type: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    resource_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    ip_address: Mapped[Optional[str]] = mapped_column(String(45), nullable=True)
    user_agent: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    meta_data: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
