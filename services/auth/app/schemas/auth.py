"""
Pydantic v2 schemas — request/response shapes for all auth endpoints.
All sensitive fields excluded from responses.
"""

from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, EmailStr, field_validator, model_validator
from app.models.user import UserRole, OrgPlan
import re


# ── Shared ────────────────────────────────────────────────────

class MessageResponse(BaseModel):
    message: str

class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int  # seconds


# ── User Schemas ──────────────────────────────────────────────

class UserBase(BaseModel):
    email: EmailStr
    full_name: Optional[str] = None

class UserCreate(UserBase):
    password: str

    @field_validator("password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        if len(v) < 10:
            raise ValueError("Password must be at least 10 characters")
        if len(v) > 128:
            raise ValueError("Password must be under 128 characters")
        if not re.search(r"[A-Z]", v):
            raise ValueError("Password must contain at least one uppercase letter")
        if not re.search(r"[a-z]", v):
            raise ValueError("Password must contain at least one lowercase letter")
        if not re.search(r"\d", v):
            raise ValueError("Password must contain at least one digit")
        if not re.search(r"[!@#$%^&*()+\-=\[\]{}|,.<>/?]", v):
            raise ValueError("Password must contain at least one special character")
        # Block common weak passwords
        COMMON = {"password1A!", "Password1!", "Admin1234!", "Jarviis123!"}
        if v in COMMON:
            raise ValueError("This password is too common. Please choose a stronger password.")
        return v

class UserResponse(BaseModel):
    id: str
    email: str
    full_name: Optional[str]
    avatar_url: Optional[str]
    is_email_verified: bool
    is_active: bool
    created_at: datetime
    last_login_at: Optional[datetime]
    # Org context
    org_id: Optional[str] = None
    org_slug: Optional[str] = None
    org_name: Optional[str] = None
    role: Optional[str] = None
    plan: Optional[str] = "free"
    sso_provider: Optional[str] = None
    # Trial
    trial_active: bool = False
    trial_hours_remaining: float = 0.0

    class Config:
        from_attributes = True

class UserUpdateRequest(BaseModel):
    full_name: Optional[str] = None
    avatar_url: Optional[str] = None


# ── Auth Schemas ──────────────────────────────────────────────

class LoginRequest(BaseModel):
    email: EmailStr
    password: str

class RefreshTokenRequest(BaseModel):
    refresh_token: str

class LogoutRequest(BaseModel):
    refresh_token: str

class PasswordChangeRequest(BaseModel):
    current_password: str
    new_password: str

    @field_validator("new_password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        if len(v) < 10:
            raise ValueError("Password must be at least 10 characters")
        if len(v) > 128:
            raise ValueError("Password must be under 128 characters")
        if not re.search(r"[A-Z]", v):
            raise ValueError("Password must contain at least one uppercase letter")
        if not re.search(r"[a-z]", v):
            raise ValueError("Password must contain at least one lowercase letter")
        if not re.search(r"\d", v):
            raise ValueError("Password must contain at least one digit")
        if not re.search(r"[!@#$%^&*()+\-=\[\]{}|,.<>/?]", v):
            raise ValueError("Password must contain at least one special character")
        # Block common weak passwords
        COMMON = {"password1A!", "Password1!", "Admin1234!", "Jarviis123!"}
        if v in COMMON:
            raise ValueError("This password is too common. Please choose a stronger password.")
        return v

class PasswordResetRequest(BaseModel):
    email: EmailStr

class PasswordResetConfirm(BaseModel):
    token: str
    new_password: str

class EmailVerificationRequest(BaseModel):
    token: str


# ── Organization Schemas ──────────────────────────────────────

class OrgCreate(BaseModel):
    name: str
    slug: str
    description: Optional[str] = None

    @field_validator("slug")
    @classmethod
    def validate_slug(cls, v: str) -> str:
        if not re.match(r"^[a-z0-9\-]{3,50}$", v):
            raise ValueError("Slug must be 3–50 lowercase alphanumeric characters or hyphens")
        return v

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        if len(v.strip()) < 2:
            raise ValueError("Organization name must be at least 2 characters")
        return v.strip()

class OrgUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    logo_url: Optional[str] = None

class OrgResponse(BaseModel):
    id: str
    name: str
    slug: str
    description: Optional[str]
    logo_url: Optional[str] = None
    plan: str
    monthly_test_run_limit: int
    monthly_test_runs_used: int
    member_count: int
    created_at: datetime

    class Config:
        from_attributes = True


# ── Member Schemas ────────────────────────────────────────────

class MemberResponse(BaseModel):
    id: str
    user_id: str
    email: str
    full_name: Optional[str]
    avatar_url: Optional[str]
    role: str
    joined_at: datetime

class MemberUpdateRequest(BaseModel):
    role: UserRole

class InviteMemberRequest(BaseModel):
    email: EmailStr
    role: UserRole = UserRole.MEMBER

class InviteResponse(BaseModel):
    id: str
    email: str
    role: str
    status: str
    expires_at: datetime
    created_at: datetime


# ── OAuth Schemas ─────────────────────────────────────────────

class OAuthCallbackRequest(BaseModel):
    code: str
    state: Optional[str] = None


# ── Onboarding Schemas ────────────────────────────────────────

class OnboardingCompleteRequest(BaseModel):
    """Sent after user signs up — creates their first org."""
    org_name: str
    org_slug: str
    use_case: Optional[str] = None  # "solo", "team", "enterprise"

class OnboardingResponse(BaseModel):
    user: UserResponse
    organization: OrgResponse
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
