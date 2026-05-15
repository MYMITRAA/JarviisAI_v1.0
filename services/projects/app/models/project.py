"""
Project-domain models.
All data is org-scoped — every query includes org_id for multi-tenancy isolation.
"""

import uuid
import enum
from datetime import datetime, timezone
from typing import Optional, List
from sqlalchemy import (
    String, Boolean, DateTime, ForeignKey, Text, Column,
    UniqueConstraint, Index, Integer, Float,
    Enum as SAEnum
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy import JSON
from app.core.database import Base


def utcnow(): return datetime.now(timezone.utc)
def new_uuid(): return str(uuid.uuid4())


class ProjectType(str, enum.Enum):
    WEB     = "web"
    ANDROID = "android"
    IOS     = "ios"
    API     = "api"
    DOCKER  = "docker"
    COBOL   = "cobol"


class TestRunStatus(str, enum.Enum):
    PENDING   = "pending"
    QUEUED    = "queued"
    CRAWLING  = "crawling"
    GENERATING = "generating"
    RUNNING   = "running"
    PASSED    = "passed"
    FAILED    = "failed"
    CANCELLED = "cancelled"
    ERROR     = "error"


class TestCaseStatus(str, enum.Enum):
    PENDING = "pending"
    PASSED  = "passed"
    FAILED  = "failed"
    SKIPPED = "skipped"
    FLAKY   = "flaky"


class TriggerType(str, enum.Enum):
    MANUAL      = "manual"
    GITHUB_PUSH = "github_push"
    GITHUB_PR   = "github_pr"
    SCHEDULED   = "scheduled"
    API         = "api"


# ── Project ───────────────────────────────────────────────────

class Project(Base):
    __tablename__ = "projects"
    __table_args__ = (
        UniqueConstraint("org_id", "slug", name="uq_project_org_slug"),
        Index("ix_projects_org_id", "org_id"),
    )

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=new_uuid)
    org_id: Mapped[str] = mapped_column(UUID(as_uuid=False), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    target_url = Column(String, nullable=True)
    project_type: Mapped[str] = mapped_column(SAEnum(ProjectType), default=ProjectType.WEB)
    project_url: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_by_id: Mapped[Optional[str]] = mapped_column(UUID(as_uuid=False), nullable=True)

    # Test configuration
    test_config: Mapped[Optional[dict]] = mapped_column(JSON, default={})
    # {browsers: ["chrome","firefox"], viewport: "desktop", auth_url: ..., auth_credentials: {...}}

    # Stats (denormalized for fast dashboard queries)
    last_run_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    last_run_status: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    total_runs: Mapped[int] = mapped_column(Integer, default=0)
    pass_rate: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    # Relationships
    test_runs: Mapped[List["TestRun"]] = relationship(back_populates="project", cascade="all, delete-orphan")
    github_integration: Mapped[Optional["GitHubIntegration"]] = relationship(back_populates="project", uselist=False, cascade="all, delete-orphan")
    environments: Mapped[List["ProjectEnvironment"]] = relationship(back_populates="project", cascade="all, delete-orphan")


# ── Project Environment ───────────────────────────────────────

class ProjectEnvironment(Base):
    """Environment configs per project (dev / staging / production)."""
    __tablename__ = "project_environments"
    __table_args__ = (
        UniqueConstraint("project_id", "name", name="uq_env_project_name"),
    )

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=new_uuid)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    org_id: Mapped[str] = mapped_column(UUID(as_uuid=False), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)  # dev / staging / production
    base_url: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    project: Mapped["Project"] = relationship(back_populates="environments")


# ── GitHub Integration ────────────────────────────────────────

class GitHubIntegration(Base):
    __tablename__ = "github_integrations"
    __table_args__ = (
        Index("ix_github_org_id", "org_id"),
    )

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=new_uuid)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), unique=True)
    org_id: Mapped[str] = mapped_column(UUID(as_uuid=False), nullable=False)

    # GitHub App installation details
    installation_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    repo_owner: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    repo_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    repo_full_name: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    default_branch: Mapped[str] = mapped_column(String(100), default="main")

    # Trigger settings
    trigger_on_push: Mapped[bool] = mapped_column(Boolean, default=True)
    trigger_on_pr: Mapped[bool] = mapped_column(Boolean, default=True)
    branch_filter: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    # Status
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_webhook_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    project: Mapped["Project"] = relationship(back_populates="github_integration")


# ── Test Run ──────────────────────────────────────────────────

class TestRun(Base):
    __tablename__ = "test_runs"
    __table_args__ = (
        Index("ix_test_runs_project_id", "project_id"),
        Index("ix_test_runs_org_id", "org_id"),
        Index("ix_test_runs_created_at", "created_at"),
        Index("ix_test_runs_status", "status"),
    )

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=new_uuid)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    org_id: Mapped[str] = mapped_column(UUID(as_uuid=False), nullable=False)

    status: Mapped[str] = mapped_column(SAEnum(TestRunStatus), default=TestRunStatus.PENDING)
    trigger_type: Mapped[str] = mapped_column(SAEnum(TriggerType), default=TriggerType.MANUAL)

    # Git context (populated from GitHub webhook)
    git_commit_sha: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    git_branch: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    git_pr_number: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    git_pr_title: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    git_commit_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    git_author: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    # Results
    total_tests: Mapped[int] = mapped_column(Integer, default=0)
    passed_tests: Mapped[int] = mapped_column(Integer, default=0)
    failed_tests: Mapped[int] = mapped_column(Integer, default=0)
    skipped_tests: Mapped[int] = mapped_column(Integer, default=0)
    flaky_tests: Mapped[int] = mapped_column(Integer, default=0)
    duration_seconds: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # AI outputs
    ai_test_plan: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    ai_summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    ai_root_cause: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    crawl_result: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    # Error state
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    error_stage: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)

    # Metadata
    environment_name: Mapped[str] = mapped_column(String(100), default="default")
    browsers: Mapped[Optional[list]] = mapped_column(JSON, default=["chromium"])
    test_metadata: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)

    # Timing
    queued_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by_id: Mapped[Optional[str]] = mapped_column(UUID(as_uuid=False), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    # Relationships
    project: Mapped["Project"] = relationship(back_populates="test_runs")
    test_cases: Mapped[List["TestCase"]] = relationship(back_populates="test_run", cascade="all, delete-orphan")

    @property
    def pass_rate(self) -> Optional[float]:
        if self.total_tests == 0:
            return None
        return round(self.passed_tests / self.total_tests * 100, 1)

    @property
    def duration_display(self) -> str:
        if not self.duration_seconds:
            return "—"
        if self.duration_seconds < 60:
            return f"{int(self.duration_seconds)}s"
        return f"{int(self.duration_seconds // 60)}m {int(self.duration_seconds % 60)}s"


# ── Test Case ─────────────────────────────────────────────────

class TestCase(Base):
    __tablename__ = "test_cases"
    __table_args__ = (
        Index("ix_test_cases_run_id", "test_run_id"),
        Index("ix_test_cases_project_id", "project_id"),
        Index("ix_test_cases_status", "status"),
    )

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=new_uuid)
    test_run_id: Mapped[str] = mapped_column(ForeignKey("test_runs.id", ondelete="CASCADE"), nullable=False)
    project_id: Mapped[str] = mapped_column(UUID(as_uuid=False), nullable=False)
    org_id: Mapped[str] = mapped_column(UUID(as_uuid=False), nullable=False)

    # Test identity
    name: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    file_path: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    test_code: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Result
    status: Mapped[str] = mapped_column(SAEnum(TestCaseStatus), default=TestCaseStatus.PENDING)
    duration_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    retry_count: Mapped[int] = mapped_column(Integer, default=0)

    # Failure details
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    error_type: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    stack_trace: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    diff_image_url: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)

    # Artifacts
    screenshot_url: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    video_url: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    trace_url: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)

    # AI analysis
    ai_failure_explanation: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    ai_fix_suggestion: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    self_healed: Mapped[bool] = mapped_column(Boolean, default=False)
    healed_selector: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Classification
    page_url: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    test_category: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    priority: Mapped[str] = mapped_column(String(20), default="medium")

    test_metadata: Mapped[Optional[dict]] = mapped_column(JSON, default={})
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    test_run: Mapped["TestRun"] = relationship(back_populates="test_cases")
