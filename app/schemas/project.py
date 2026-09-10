"""Project schemas (reference tenant-scoped resource)."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

ProjectStatus = Literal["draft", "active", "done"]


class ProjectCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    description: str | None = Field(None, max_length=2000)
    status: ProjectStatus = "draft"


class ProjectUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=100)
    description: str | None = Field(None, max_length=2000)
    status: ProjectStatus | None = None


class ProjectResponse(BaseModel):
    id: str
    name: str
    description: str | None
    status: ProjectStatus
    created_by: str | None
    created_at: datetime
    updated_at: datetime


class ProjectListResponse(BaseModel):
    items: list[ProjectResponse]
    total: int
    page: int
    page_size: int
