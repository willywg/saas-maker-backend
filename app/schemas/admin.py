"""Admin request/response schemas."""

import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr


# --- Auth Schemas ---
class AdminLoginRequest(BaseModel):
    """Admin login request - uses JSON body, not form-data."""

    email: EmailStr
    password: str


class AdminAuthUser(BaseModel):
    """Admin user context extracted from JWT."""

    admin_id: uuid.UUID
    email: str
    role: str


class AdminLoginResponse(BaseModel):
    """Login response with tokens."""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class AdminRefreshRequest(BaseModel):
    """Refresh token request."""

    refresh_token: str


# --- AdminUser Schemas ---
class AdminUserResponse(BaseModel):
    """Admin user info response."""

    id: uuid.UUID
    email: str
    full_name: str
    role: str
    is_active: bool
    created_at: datetime
    last_login_at: datetime | None


# --- Organization Schemas (for admin) ---
class OrganizationListItem(BaseModel):
    """Organization in list view."""

    id: uuid.UUID
    name: str
    slug: str
    is_active: bool
    created_at: datetime
    member_count: int


class OrganizationMemberInfo(BaseModel):
    """Member info within organization detail."""

    id: uuid.UUID
    email: str
    full_name: str | None
    role: str
    joined_at: datetime


class OrganizationDetailAdmin(BaseModel):
    """Organization detail with members."""

    id: uuid.UUID
    name: str
    slug: str
    is_active: bool
    created_at: datetime
    updated_at: datetime
    members: list[OrganizationMemberInfo]


class OrganizationUpdateAdmin(BaseModel):
    """Organization update request."""

    name: str | None = None
    slug: str | None = None
    is_active: bool | None = None


class StatusToggleRequest(BaseModel):
    """Request to toggle active status."""

    is_active: bool


# --- User Schemas (for admin) ---
class UserOrganizationInfo(BaseModel):
    """Organization info for user list."""

    id: uuid.UUID
    name: str
    slug: str
    role: str


class UserListItem(BaseModel):
    """User in list view."""

    id: uuid.UUID
    email: str
    full_name: str | None
    is_active: bool
    created_at: datetime
    last_login_at: datetime | None
    organization: UserOrganizationInfo | None  # Primary organization


class MembershipInfo(BaseModel):
    """Membership info for user detail."""

    organization_id: uuid.UUID
    organization_name: str
    role: str
    joined_at: datetime


class UserDetailAdmin(BaseModel):
    """User detail with memberships."""

    id: uuid.UUID
    email: str
    full_name: str | None
    is_active: bool
    email_verified: bool
    created_at: datetime
    last_login_at: datetime | None
    memberships: list[MembershipInfo]


class UserUpdateAdmin(BaseModel):
    """User update request."""

    full_name: str | None = None
    is_active: bool | None = None


# --- Pagination ---
class PaginatedResponse[T](BaseModel):
    """Generic paginated response."""

    items: list[T]
    total: int
    page: int
    page_size: int
    total_pages: int
