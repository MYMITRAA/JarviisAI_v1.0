"""SSO domain models — supports SAML 2.0 and OIDC providers per organization."""

import uuid, enum
from datetime import datetime, timezone
from typing import Optional
from sqlalchemy import String, Boolean, DateTime, Text, Enum as SAEnum, Index
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID, JSONB
from app.core.database import Base

def utcnow(): return datetime.now(timezone.utc)
def new_uuid(): return str(uuid.uuid4())


class SsoProtocol(str, enum.Enum):
    SAML   = "saml"
    OIDC   = "oidc"     # OpenID Connect
    OAUTH2 = "oauth2"   # Generic OAuth2


class SsoProvider(Base):
    """One SSO configuration per organization."""
    __tablename__ = "sso_providers"
    __table_args__ = (
        Index("ix_sso_providers_org_id", "org_id"),
        Index("ix_sso_providers_slug", "slug"),
    )

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=new_uuid)
    org_id: Mapped[str] = mapped_column(UUID(as_uuid=False), nullable=False, unique=True)
    slug: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)  # e.g. "acme-corp"
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    protocol: Mapped[str] = mapped_column(SAEnum(SsoProtocol), default=SsoProtocol.SAML)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    # SAML config
    idp_entity_id: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    idp_sso_url: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    idp_slo_url: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    idp_certificate: Mapped[Optional[str]] = mapped_column(Text, nullable=True)   # X.509 PEM
    idp_metadata_url: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)

    # OIDC config
    oidc_issuer: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    oidc_client_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    oidc_client_secret_enc: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # encrypted
    oidc_discovery_url: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    oidc_scopes: Mapped[Optional[list]] = mapped_column(JSONB, default=["openid", "email", "profile"])

    # Attribute mapping (IdP attribute → JarviisAI field)
    attribute_mapping: Mapped[Optional[dict]] = mapped_column(JSONB, default={
        "email": "email",
        "firstName": "given_name",
        "lastName": "family_name",
        "groups": "groups",
    })

    # Enforcement
    enforce_sso: Mapped[bool] = mapped_column(Boolean, default=False)  # If True, password login disabled
    auto_provision: Mapped[bool] = mapped_column(Boolean, default=True)  # Create user on first SSO login
    default_role: Mapped[str] = mapped_column(String(50), default="member")
    allowed_domains: Mapped[Optional[list]] = mapped_column(JSONB, default=[])  # e.g. ["acme.com"]

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class SsoSession(Base):
    """Tracks active SSO sessions for SLO (Single Logout) support."""
    __tablename__ = "sso_sessions"
    __table_args__ = (Index("ix_sso_sessions_org_id", "org_id"),)

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=new_uuid)
    org_id: Mapped[str] = mapped_column(UUID(as_uuid=False), nullable=False)
    user_id: Mapped[str] = mapped_column(UUID(as_uuid=False), nullable=False)
    provider_id: Mapped[str] = mapped_column(UUID(as_uuid=False), nullable=False)
    saml_session_index: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    oidc_session_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    access_token: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class SsoAuditLog(Base):
    """Security audit log for all SSO events."""
    __tablename__ = "sso_audit_logs"
    __table_args__ = (Index("ix_sso_audit_org_id", "org_id"),)

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=new_uuid)
    org_id: Mapped[str] = mapped_column(UUID(as_uuid=False), nullable=False)
    user_id: Mapped[Optional[str]] = mapped_column(UUID(as_uuid=False), nullable=True)
    event: Mapped[str] = mapped_column(String(100), nullable=False)
    # login_success | login_failure | logout | provision | error
    details: Mapped[Optional[dict]] = mapped_column(JSONB, default={})
    ip_address: Mapped[Optional[str]] = mapped_column(String(45), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
