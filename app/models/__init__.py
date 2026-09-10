"""
Models package.

Imports all models to ensure they're registered with SQLModel metadata
and discovered by Alembic for migrations.
"""

from app.models.admin import AdminUser
from app.models.project import Project
from app.models.tenant import (
    EmailVerificationToken,
    InviteToken,
    Organization,
    OrganizationMember,
    PasswordResetToken,
    RefreshToken,
    User,
)

__all__ = [
    "Organization",
    "User",
    "OrganizationMember",
    "InviteToken",
    "PasswordResetToken",
    "EmailVerificationToken",
    "RefreshToken",
    "AdminUser",
    "Project",
    # generator:models
]
