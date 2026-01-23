"""Multi-tenant models: Organizations, Users, and Memberships."""

import secrets
import uuid
from datetime import datetime

from sqlalchemy import Column, ForeignKey as SAForeignKey
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlmodel import Field, SQLModel, UniqueConstraint


class Organization(SQLModel, table=True):
    """
    Organization/Tenant - represents a company/team using the service.

    Each organization has isolated data.
    Users can belong to multiple organizations with different roles.
    """

    __tablename__ = "organizations"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)

    # Organization info
    name: str = Field(max_length=100, nullable=False)
    slug: str = Field(
        max_length=100,
        unique=True,
        index=True,
        nullable=False,
        description="URL-safe identifier (e.g., 'acme-corp')",
    )

    # Settings
    is_active: bool = Field(default=True)

    # Timestamps
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class User(SQLModel, table=True):
    """
    User account - can belong to multiple organizations.

    Authentication is handled at user level, authorization at org level.
    """

    __tablename__ = "users"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)

    # Credentials
    email: str = Field(
        max_length=255,
        unique=True,
        index=True,
        nullable=False,
        description="Email (case-insensitive, stored lowercase)",
    )
    password_hash: str = Field(max_length=255, nullable=False)

    # Profile
    full_name: str | None = Field(default=None, max_length=100)

    # Account status
    is_active: bool = Field(default=True)
    email_verified: bool = Field(default=False)

    # Timestamps
    created_at: datetime = Field(default_factory=datetime.utcnow)
    last_login_at: datetime | None = Field(default=None)


class OrganizationMember(SQLModel, table=True):
    """
    Many-to-many relationship between Users and Organizations.

    Stores the role of each user within each organization.
    A user can have different roles in different organizations.
    """

    __tablename__ = "organization_members"
    __table_args__ = (UniqueConstraint("organization_id", "user_id", name="uq_org_user"),)

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)

    # Relationships with CASCADE delete
    organization_id: uuid.UUID = Field(
        sa_column=Column(
            PGUUID(as_uuid=True),
            SAForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        )
    )
    user_id: uuid.UUID = Field(
        sa_column=Column(
            PGUUID(as_uuid=True),
            SAForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        )
    )

    # Role within this organization
    role: str = Field(
        max_length=20, nullable=False, description="Role: 'owner' | 'admin' | 'member'"
    )

    # Timestamps
    created_at: datetime = Field(default_factory=datetime.utcnow)


class InviteToken(SQLModel, table=True):
    """
    Invitation tokens for adding members to organizations.

    Tokens are single-use and expire after a configurable period.
    The invited user uses the token to create their account and join the org.
    """

    __tablename__ = "invite_tokens"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)

    # Organization being invited to
    organization_id: uuid.UUID = Field(
        sa_column=Column(
            PGUUID(as_uuid=True),
            SAForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        )
    )

    # Invitation details
    email: str = Field(max_length=255, index=True, nullable=False)
    role: str = Field(
        max_length=20, nullable=False, description="Role to assign: 'admin' | 'member'"
    )

    # Token (URL-safe, unique)
    token: str = Field(max_length=64, unique=True, index=True, nullable=False)

    # Expiration and usage tracking
    expires_at: datetime = Field(nullable=False)
    accepted_at: datetime | None = Field(default=None, description="Set when token is used")

    # Who created this invitation
    created_by: uuid.UUID = Field(
        sa_column=Column(
            PGUUID(as_uuid=True),
            SAForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        )
    )

    # Timestamps
    created_at: datetime = Field(default_factory=datetime.utcnow)

    @classmethod
    def generate_token(cls) -> str:
        """Generate a secure URL-safe token."""
        return secrets.token_urlsafe(32)
