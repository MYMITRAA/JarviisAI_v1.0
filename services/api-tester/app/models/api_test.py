"""API testing domain models."""

import uuid, enum
from datetime import datetime, timezone
from typing import Optional, List
from sqlalchemy import String, Boolean, DateTime, ForeignKey, Text, Integer, Float, Enum as SAEnum, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID, JSONB
from app.core.database import Base

def utcnow(): return datetime.now(timezone.utc)
def new_uuid(): return str(uuid.uuid4())


class SpecFormat(str, enum.Enum):
    OPENAPI_3   = "openapi_3"
    OPENAPI_2   = "openapi_2"   # Swagger 2.0
    POSTMAN     = "postman"
    GRAPHQL     = "graphql"
    GRPC        = "grpc"


class ApiTestStatus(str, enum.Enum):
    PENDING  = "pending"
    RUNNING  = "running"
    PASSED   = "passed"
    FAILED   = "failed"
    ERROR    = "error"


class ApiTestType(str, enum.Enum):
    SCHEMA_VALIDATION   = "schema_validation"    # Response matches schema
    STATUS_CODE         = "status_code"          # Expected HTTP code
    RESPONSE_TIME       = "response_time"        # Latency SLA
    AUTH                = "auth"                 # Auth/401 gates work
    CONTRACT            = "contract"             # Consumer contract tests
    MUTATION            = "mutation"             # POST/PUT/DELETE correctness
    PAGINATION          = "pagination"           # Pagination works
    ERROR_HANDLING      = "error_handling"       # 4xx/5xx are correct
    SECURITY            = "security"             # CORS, rate limits, injection


class ApiSpec(Base):
    __tablename__ = "api_specs"
    __table_args__ = (Index("ix_api_specs_project_id", "project_id"),)

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=new_uuid)
    org_id: Mapped[str] = mapped_column(UUID(as_uuid=False), nullable=False)
    project_id: Mapped[str] = mapped_column(UUID(as_uuid=False), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    format: Mapped[str] = mapped_column(SAEnum(SpecFormat), default=SpecFormat.OPENAPI_3)
    base_url: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    spec_content: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    spec_url: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    version: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    endpoint_count: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    auth_config: Mapped[Optional[dict]] = mapped_column(JSONB, default={})
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    test_runs: Mapped[List["ApiTestRun"]] = relationship(back_populates="spec", cascade="all, delete-orphan")


class ApiTestRun(Base):
    __tablename__ = "api_test_runs"
    __table_args__ = (Index("ix_api_runs_spec_id", "spec_id"), Index("ix_api_runs_project_id", "project_id"))

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=new_uuid)
    spec_id: Mapped[str] = mapped_column(ForeignKey("api_specs.id", ondelete="CASCADE"))
    project_id: Mapped[str] = mapped_column(UUID(as_uuid=False), nullable=False)
    org_id: Mapped[str] = mapped_column(UUID(as_uuid=False), nullable=False)

    status: Mapped[str] = mapped_column(SAEnum(ApiTestStatus), default=ApiTestStatus.PENDING)
    total_endpoints: Mapped[int] = mapped_column(Integer, default=0)
    tested_endpoints: Mapped[int] = mapped_column(Integer, default=0)
    passed: Mapped[int] = mapped_column(Integer, default=0)
    failed: Mapped[int] = mapped_column(Integer, default=0)
    errors: Mapped[int] = mapped_column(Integer, default=0)
    duration_seconds: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    ai_summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    environment: Mapped[str] = mapped_column(String(100), default="default")

    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    spec: Mapped["ApiSpec"] = relationship(back_populates="test_runs")
    results: Mapped[List["ApiTestResult"]] = relationship(back_populates="run", cascade="all, delete-orphan")

    @property
    def pass_rate(self) -> Optional[float]:
        total = self.passed + self.failed
        return round(self.passed / total * 100, 1) if total > 0 else None


class ApiTestResult(Base):
    __tablename__ = "api_test_results"
    __table_args__ = (Index("ix_api_results_run_id", "run_id"),)

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=new_uuid)
    run_id: Mapped[str] = mapped_column(ForeignKey("api_test_runs.id", ondelete="CASCADE"))
    project_id: Mapped[str] = mapped_column(UUID(as_uuid=False), nullable=False)

    endpoint_method: Mapped[str] = mapped_column(String(10), nullable=False)
    endpoint_path: Mapped[str] = mapped_column(String(512), nullable=False)
    test_type: Mapped[str] = mapped_column(SAEnum(ApiTestType), default=ApiTestType.SCHEMA_VALIDATION)
    test_name: Mapped[str] = mapped_column(String(500), nullable=False)
    status: Mapped[str] = mapped_column(SAEnum(ApiTestStatus), default=ApiTestStatus.PENDING)

    # Request details
    request_url: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)
    request_headers: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    request_body: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Response details
    response_status_code: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    response_headers: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    response_body_preview: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    response_time_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # Result
    expected_status: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    actual_status: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    schema_valid: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    schema_errors: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True)
    assertion_errors: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # AI analysis
    ai_insight: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    run: Mapped["ApiTestRun"] = relationship(back_populates="results")
