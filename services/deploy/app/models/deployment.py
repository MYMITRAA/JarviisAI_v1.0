"""
Deploy domain models.
Everything is org-scoped for multi-tenancy.
"""

import uuid
import enum
from datetime import datetime, timezone
from typing import Optional, List
from sqlalchemy import (
    String, Boolean, DateTime, ForeignKey, Text,
    Integer, Float, Enum as SAEnum, UniqueConstraint, Index
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID, JSONB
from app.core.database import Base


def utcnow(): return datetime.now(timezone.utc)
def new_uuid(): return str(uuid.uuid4())


class DeploymentStatus(str, enum.Enum):
    PENDING   = "pending"
    BUILDING  = "building"
    PUSHING   = "pushing"
    DEPLOYING = "deploying"
    RUNNING   = "running"        # Healthy and live
    DEGRADED  = "degraded"       # Running but unhealthy
    FAILED    = "failed"
    ROLLED_BACK = "rolled_back"
    CANCELLED = "cancelled"


class EnvironmentTier(str, enum.Enum):
    DEVELOPMENT = "development"
    STAGING     = "staging"
    PRODUCTION  = "production"
    CUSTOM      = "custom"


class DeployStrategy(str, enum.Enum):
    ROLLING   = "rolling"       # Replace instances one by one
    BLUE_GREEN = "blue_green"   # Full parallel swap
    CANARY    = "canary"        # Gradual traffic shift
    RECREATE  = "recreate"      # Stop all, then start new


class ServerProvider(str, enum.Enum):
    SSH       = "ssh"           # Raw SSH + docker compose
    AWS_EC2   = "aws_ec2"
    GCP_GCE   = "gcp_gce"
    AZURE_VM  = "azure_vm"
    DO        = "digitalocean"
    HETZNER   = "hetzner"


# ── Target Server ─────────────────────────────────────────────

class DeployServer(Base):
    __tablename__ = "deploy_servers"
    __table_args__ = (
        UniqueConstraint("org_id", "name", name="uq_server_org_name"),
        Index("ix_deploy_servers_org_id", "org_id"),
    )

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=new_uuid)
    org_id: Mapped[str] = mapped_column(UUID(as_uuid=False), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    provider: Mapped[str] = mapped_column(SAEnum(ServerProvider), default=ServerProvider.SSH)
    host: Mapped[str] = mapped_column(String(255), nullable=False)
    port: Mapped[int] = mapped_column(Integer, default=22)
    ssh_user: Mapped[str] = mapped_column(String(100), default="deploy")

    # Encrypted credentials (encrypted at rest using SECRET_KEY)
    ssh_private_key_enc: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    docker_host: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    cloud_credentials_enc: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Server metadata
    os_type: Mapped[str] = mapped_column(String(50), default="linux")
    docker_version: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    deploy_path: Mapped[str] = mapped_column(String(512), default="/opt/deploy")

    # Health
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_ping_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    last_ping_ok: Mapped[bool] = mapped_column(Boolean, default=False)
    tags: Mapped[Optional[dict]] = mapped_column(JSONB, default={})

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    environments: Mapped[List["DeployEnvironment"]] = relationship(back_populates="server")


# ── Deploy Environment ────────────────────────────────────────

class DeployEnvironment(Base):
    """A project × tier × server slot — e.g. "MyApp → Staging → server-eu-1"."""
    __tablename__ = "deploy_environments"
    __table_args__ = (
        UniqueConstraint("project_id", "tier", name="uq_env_project_tier"),
        Index("ix_deploy_envs_org_id", "org_id"),
    )

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=new_uuid)
    org_id: Mapped[str] = mapped_column(UUID(as_uuid=False), nullable=False)
    project_id: Mapped[str] = mapped_column(UUID(as_uuid=False), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    tier: Mapped[str] = mapped_column(SAEnum(EnvironmentTier), default=EnvironmentTier.STAGING)

    # Server target
    server_id: Mapped[Optional[str]] = mapped_column(ForeignKey("deploy_servers.id"), nullable=True)
    deploy_path: Mapped[str] = mapped_column(String(512), default="/opt/deploy")
    compose_file: Mapped[str] = mapped_column(String(255), default="docker-compose.yml")

    # Configuration
    env_vars_enc: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # encrypted JSON
    auto_deploy_branch: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    strategy: Mapped[str] = mapped_column(SAEnum(DeployStrategy), default=DeployStrategy.ROLLING)
    health_check_url: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    health_check_timeout_s: Mapped[int] = mapped_column(Integer, default=60)
    requires_test_pass: Mapped[bool] = mapped_column(Boolean, default=True)

    # State
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    current_deployment_id: Mapped[Optional[str]] = mapped_column(UUID(as_uuid=False), nullable=True)
    last_deployed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    current_image_tag: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    server: Mapped[Optional["DeployServer"]] = relationship(back_populates="environments")
    deployments: Mapped[List["Deployment"]] = relationship(back_populates="environment")


# ── Deployment ────────────────────────────────────────────────

class Deployment(Base):
    __tablename__ = "deployments"
    __table_args__ = (
        Index("ix_deployments_org_id", "org_id"),
        Index("ix_deployments_environment_id", "environment_id"),
        Index("ix_deployments_created_at", "created_at"),
        Index("ix_deployments_status", "status"),
    )

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=new_uuid)
    org_id: Mapped[str] = mapped_column(UUID(as_uuid=False), nullable=False)
    project_id: Mapped[str] = mapped_column(UUID(as_uuid=False), nullable=False)
    environment_id: Mapped[str] = mapped_column(ForeignKey("deploy_environments.id"), nullable=False)
    triggered_by: Mapped[Optional[str]] = mapped_column(UUID(as_uuid=False), nullable=True)

    # Git context
    git_commit_sha: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    git_branch: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    git_tag: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    git_commit_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Docker
    image_repository: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    image_tag: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    image_digest: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    # Status
    status: Mapped[str] = mapped_column(SAEnum(DeploymentStatus), default=DeploymentStatus.PENDING)
    strategy: Mapped[str] = mapped_column(SAEnum(DeployStrategy), default=DeployStrategy.ROLLING)

    # Timing
    queued_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_seconds: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # Logs and artifacts
    deploy_log: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    error_stage: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)

    # Health check result
    health_check_passed: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    health_check_url: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    health_check_response_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # Previous state (for rollback)
    previous_image_tag: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    previous_deployment_id: Mapped[Optional[str]] = mapped_column(UUID(as_uuid=False), nullable=True)
    is_rollback: Mapped[bool] = mapped_column(Boolean, default=False)

    # Test gate
    test_run_id: Mapped[Optional[str]] = mapped_column(UUID(as_uuid=False), nullable=True)
    test_gate_passed: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)

    metadata: Mapped[Optional[dict]] = mapped_column(JSONB, default={})
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    environment: Mapped["DeployEnvironment"] = relationship(back_populates="deployments")
    rollback_snapshot: Mapped[Optional["RollbackSnapshot"]] = relationship(
        back_populates="deployment", uselist=False, cascade="all, delete-orphan"
    )

    @property
    def duration_display(self) -> str:
        if not self.duration_seconds:
            return "—"
        if self.duration_seconds < 60:
            return f"{int(self.duration_seconds)}s"
        return f"{int(self.duration_seconds // 60)}m {int(self.duration_seconds % 60)}s"


# ── Rollback Snapshot ─────────────────────────────────────────

class RollbackSnapshot(Base):
    """Captures the full state before a deployment — enables one-click rollback."""
    __tablename__ = "rollback_snapshots"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=new_uuid)
    deployment_id: Mapped[str] = mapped_column(
        ForeignKey("deployments.id", ondelete="CASCADE"), unique=True
    )
    org_id: Mapped[str] = mapped_column(UUID(as_uuid=False), nullable=False)
    project_id: Mapped[str] = mapped_column(UUID(as_uuid=False), nullable=False)

    # Captured state
    image_tag: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    compose_content: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    env_vars_snapshot_enc: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    running_containers: Mapped[Optional[dict]] = mapped_column(JSONB, default={})
    server_state: Mapped[Optional[dict]] = mapped_column(JSONB, default={})

    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    deployment: Mapped["Deployment"] = relationship(back_populates="rollback_snapshot")
