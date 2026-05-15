from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, HttpUrl, field_validator
from app.models.project import ProjectType, TestRunStatus, TriggerType, TestCaseStatus
import re


# ── Project schemas ───────────────────────────────────────────

class ProjectCreate(BaseModel):
    name: str
    slug: str
    description: Optional[str] = None
    target_url: str | None = None
    project_type: ProjectType = ProjectType.WEB
    project_url: Optional[str] = None
    test_config: Optional[Dict[str, Any]] = {}

    @field_validator("slug")
    @classmethod
    def validate_slug(cls, v: str) -> str:
        if not re.match(r"^[a-z0-9\-]{2,80}$", v):
            raise ValueError("Slug must be 2-80 lowercase alphanumeric characters or hyphens")
        return v

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        if len(v.strip()) < 2:
            raise ValueError("Project name must be at least 2 characters")
        return v.strip()


class ProjectUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    project_url: Optional[str] = None
    test_config: Optional[Dict[str, Any]] = None


class ProjectResponse(BaseModel):
    id: str
    org_id: str
    name: str
    slug: str
    description: Optional[str]
    target_url: str | None = None
    project_type: str
    project_url: Optional[str]
    is_active: bool
    last_run_at: Optional[datetime]
    last_run_status: Optional[str]
    total_runs: int
    pass_rate: Optional[float]
    test_config: Optional[Dict[str, Any]]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class ProjectListResponse(BaseModel):
    projects: List[ProjectResponse]
    total: int
    page: int
    page_size: int


# ── GitHub Integration schemas ────────────────────────────────

class GitHubIntegrationCreate(BaseModel):
    repo_full_name: str  # "owner/repo"
    installation_id: Optional[str] = None
    default_branch: str = "main"
    trigger_on_push: bool = True
    trigger_on_pr: bool = True
    branch_filter: Optional[str] = None

    @field_validator("repo_full_name")
    @classmethod
    def validate_repo(cls, v: str) -> str:
        if "/" not in v or len(v.split("/")) != 2:
            raise ValueError("repo_full_name must be in format 'owner/repo'")
        return v


class GitHubIntegrationResponse(BaseModel):
    id: str
    project_id: str
    repo_full_name: Optional[str]
    repo_owner: Optional[str]
    repo_name: Optional[str]
    default_branch: str
    trigger_on_push: bool
    trigger_on_pr: bool
    is_active: bool
    last_webhook_at: Optional[datetime]

    class Config:
        from_attributes = True


# ── GitHub Webhook schemas ────────────────────────────────────

class GitHubWebhookPush(BaseModel):
    ref: str
    after: str  # commit SHA
    repository: Dict[str, Any]
    head_commit: Optional[Dict[str, Any]] = None
    sender: Optional[Dict[str, Any]] = None


class GitHubWebhookPR(BaseModel):
    action: str
    number: int
    pull_request: Dict[str, Any]
    repository: Dict[str, Any]
    sender: Optional[Dict[str, Any]] = None


# ── Test Run schemas ──────────────────────────────────────────

class TestRunCreate(BaseModel):
    project_id: str
    environment_name: str = "default"
    browsers: List[str] = ["chromium"]
    trigger_type: TriggerType = TriggerType.MANUAL
    git_branch: Optional[str] = None
    git_commit_sha: Optional[str] = None
    git_pr_number: Optional[int] = None
    test_metadata: Optional[Dict[str, Any]] = {}


class TestRunResponse(BaseModel):
    id: str
    project_id: str
    org_id: str
    status: str
    trigger_type: str
    git_commit_sha: Optional[str]
    git_branch: Optional[str]
    git_pr_number: Optional[int]
    git_author: Optional[str]
    git_commit_message: Optional[str]
    total_tests: int
    passed_tests: int
    failed_tests: int
    skipped_tests: int
    flaky_tests: int
    duration_seconds: Optional[float]
    pass_rate: Optional[float]
    duration_display: str
    ai_summary: Optional[str]
    error_message: Optional[str]
    error_stage: Optional[str]
    environment_name: str
    browsers: Optional[list]
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    created_at: datetime

    class Config:
        from_attributes = True


class TestRunListResponse(BaseModel):
    runs: List[TestRunResponse]
    total: int
    page: int
    page_size: int


# ── Test Case schemas ─────────────────────────────────────────

class TestCaseResponse(BaseModel):
    id: str
    test_run_id: str
    name: str
    description: Optional[str]
    status: str
    duration_ms: Optional[int]
    retry_count: int
    error_message: Optional[str]
    error_type: Optional[str]
    stack_trace: Optional[str]
    screenshot_url: Optional[str]
    video_url: Optional[str]
    trace_url: Optional[str]
    ai_failure_explanation: Optional[str]
    ai_fix_suggestion: Optional[str]
    self_healed: bool
    page_url: Optional[str]
    test_category: Optional[str]
    priority: str
    created_at: datetime

    class Config:
        from_attributes = True


class TestCaseListResponse(BaseModel):
    cases: List[TestCaseResponse]
    total: int


# ── WebSocket event schemas ───────────────────────────────────

class TestRunEvent(BaseModel):
    event: str  # "status_update" | "test_result" | "log" | "complete"
    run_id: str
    data: Dict[str, Any]
    timestamp: datetime


class TestStatusUpdate(BaseModel):
    run_id: str
    status: TestRunStatus
    stage: Optional[str] = None
    message: Optional[str] = None
    progress: Optional[int] = None  # 0-100


# ── Dashboard stats schema ────────────────────────────────────

class ProjectStats(BaseModel):
    total_projects: int = 0
    total_runs_today: int = 0
    pass_rate_today: Optional[float] = 0.0
    failed_runs_today: int = 0
    active_runs: int = 0
    tests_run_today: int = 0
