"""Project: reference tenant-scoped resource.

This module is the canonical example of a resource that belongs to one
organization. Every row carries `organization_id`, and every query in
`project_service` filters by it. Copy this shape for new resources.
"""

import uuid
from datetime import datetime

from sqlalchemy import Column, Text
from sqlalchemy import ForeignKey as SAForeignKey
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlmodel import Field, SQLModel

from app.core.time import utcnow

PROJECT_STATUSES = ("draft", "active", "done")


class Project(SQLModel, table=True):
    __tablename__ = "projects"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)

    # Tenant scope: deleting the organization deletes its projects
    organization_id: uuid.UUID = Field(
        sa_column=Column(
            PGUUID(as_uuid=True),
            SAForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        )
    )

    # Audit: who created it. Kept when the user is removed.
    created_by: uuid.UUID | None = Field(
        default=None,
        sa_column=Column(
            PGUUID(as_uuid=True),
            SAForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )

    # Fields
    name: str = Field(max_length=100, nullable=False)
    description: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    status: str = Field(default="draft", max_length=20, nullable=False)

    # Timestamps
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)
