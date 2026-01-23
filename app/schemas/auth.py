"""Authentication request/response schemas."""

import uuid
from dataclasses import dataclass
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=72)
    full_name: str | None = None
    organization_name: str = Field(min_length=1, max_length=100)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    refresh_token: str


class UserResponse(BaseModel):
    id: str
    email: str
    full_name: str | None
    organization_id: str
    organization_name: str
    role: str


class InviteInfoResponse(BaseModel):
    """Public info about an invitation (for frontend form)."""

    email: str
    organization_name: str
    role: str
    invited_by_name: str
    expires_at: datetime


class AcceptInviteRequest(BaseModel):
    """Request to accept an invitation and create account."""

    token: str
    full_name: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=8, max_length=72)


@dataclass
class AuthUser:
    """
    Represents an authenticated user with their context.

    Populated from JWT token payload.
    """

    user_id: uuid.UUID
    email: str
    organization_id: uuid.UUID
    role: str  # "owner" | "admin" | "member"

    def has_role(self, required_role: str) -> bool:
        """
        Check if user has at least the required role.

        Role hierarchy: member < admin < owner
        """
        roles_hierarchy = ["member", "admin", "owner"]

        try:
            user_level = roles_hierarchy.index(self.role)
            required_level = roles_hierarchy.index(required_role)
            return user_level >= required_level
        except ValueError:
            return False
