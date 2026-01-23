"""Organization-related Pydantic schemas."""

from datetime import datetime

from pydantic import BaseModel, EmailStr, Field


class OrganizationResponse(BaseModel):
    id: str
    name: str
    slug: str
    is_active: bool
    created_at: datetime
    updated_at: datetime


class OrganizationUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=100)
    slug: str | None = Field(None, min_length=1, max_length=100)


class MemberResponse(BaseModel):
    id: str
    email: str
    full_name: str | None
    role: str
    is_active: bool
    joined_at: datetime


class InviteMemberRequest(BaseModel):
    email: EmailStr
    role: str = Field(..., pattern="^(admin|member)$")


class ChangeRoleRequest(BaseModel):
    role: str = Field(..., pattern="^(owner|admin|member)$")


class InviteResponse(BaseModel):
    """Response when admin creates an invitation."""

    invite_url: str
    token: str
    email: str
    role: str
    expires_at: datetime
    message: str = "Share this link with the user. It can only be used once."
