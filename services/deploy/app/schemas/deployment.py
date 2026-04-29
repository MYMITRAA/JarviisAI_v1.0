from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, field_validator
from app.models.deployment import (
    DeploymentStatus, EnvironmentTier, DeployStrategy, ServerProvider
)


# ── Server schemas ────────────────────────────────────────────

class ServerCreate(BaseModel):
    name: str
    host: str
    port: int = 22
    ssh_user: str = "deploy"
    ssh_private_key: Optional[str] = None   # PEM content — stored encrypted
    deploy_path: str = "/opt/deploy"
    provider: ServerProvider = ServerProvider.SSH
    tags: Optional[Dict[str, str]] = {}


class ServerResponse(BaseModel):
    id: str
    org_id: str
    name: str
    host: str
    port: int
    ssh_user: str
    deploy_path: str
    provider: str
    is_active: bool
    last_ping_ok: bool
    last_ping_at: Optional[datetime]
    docker_version: Optional[str]
    tags: Optional[dict]
    created_at: datetime

    class Config:
        from_attributes = True


class ServerPingResult(BaseModel):
    server_id: str
    reachable: bool
    docker_available: bool
    docker_version: Optional[str]
    latency_ms: Optional[int]
    error: Optional[str]


# ── Environment schemas ───────────────────────────────────────

class EnvironmentCreate(BaseModel):
    name: str
    tier: EnvironmentTier
    server_id: Optional[str] = None
    deploy_path: str = "/opt/deploy"
    compose_file: str = "docker-compose.yml"
    strategy: DeployStrategy = DeployStrategy.ROLLING
    health_check_url: Optional[str] = None
    requires_test_pass: bool = True
    auto_deploy_branch: Optional[str] = None
    env_vars: Optional[Dict[str, str]] = {}


class EnvironmentUpdate(BaseModel):
    server_id: Optional[str] = None
    health_check_url: Optional[str] = None
    strategy: Optional[DeployStrategy] = None
    env_vars: Optional[Dict[str, str]] = None
    requires_test_pass: Optional[bool] = None
    auto_deploy_branch: Optional[str] = None


class EnvironmentResponse(BaseModel):
    id: str
    org_id: str
    project_id: str
    name: str
    tier: str
    deploy_path: str
    compose_file: str
    strategy: str
    health_check_url: Optional[str]
    requires_test_pass: bool
    auto_deploy_branch: Optional[str]
    is_active: bool
    last_deployed_at: Optional[datetime]
    current_image_tag: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True


# ── Deployment schemas ────────────────────────────────────────

class DeploymentCreate(BaseModel):
    environment_id: str
    git_commit_sha: Optional[str] = None
    git_branch: Optional[str] = None
    git_tag: Optional[str] = None
    image_repository: Optional[str] = None
    image_tag: Optional[str] = None
    strategy: Optional[DeployStrategy] = None
    test_run_id: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = {}


class DeploymentResponse(BaseModel):
    id: str
    org_id: str
    project_id: str
    environment_id: str
    git_commit_sha: Optional[str]
    git_branch: Optional[str]
    git_tag: Optional[str]
    git_commit_message: Optional[str]
    image_repository: Optional[str]
    image_tag: Optional[str]
    status: str
    strategy: str
    duration_seconds: Optional[float]
    duration_display: str
    health_check_passed: Optional[bool]
    health_check_response_ms: Optional[int]
    error_message: Optional[str]
    error_stage: Optional[str]
    is_rollback: bool
    test_gate_passed: Optional[bool]
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    created_at: datetime

    class Config:
        from_attributes = True


class DeploymentListResponse(BaseModel):
    deployments: List[DeploymentResponse]
    total: int
    page: int
    page_size: int


class RollbackRequest(BaseModel):
    deployment_id: str
    reason: Optional[str] = None


# ── Promotion schemas ─────────────────────────────────────────

class PromoteRequest(BaseModel):
    """Promote a deployment from one tier to the next."""
    from_environment_id: str
    to_environment_id: str
    image_tag: Optional[str] = None   # If None, uses current image from source env
    run_tests_first: bool = True
    reason: Optional[str] = None


class PromoteResponse(BaseModel):
    deployment_id: str
    from_tier: str
    to_tier: str
    image_tag: str
    status: str
    message: str


# ── Deploy log streaming ──────────────────────────────────────

class DeployLogEvent(BaseModel):
    deployment_id: str
    event: str  # "log" | "stage_change" | "complete" | "error"
    stage: Optional[str]
    message: str
    timestamp: datetime


# ── Dashboard stats ────────────────────────────────────────────

class DeployStats(BaseModel):
    total_deployments: int
    deployments_today: int
    success_rate_7d: Optional[float]
    avg_deploy_time_seconds: Optional[float]
    active_deployments: int
    environments_count: int
