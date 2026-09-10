"""Project service (reference tenant-scoped resource).

Rule: every function takes `organization_id` and scopes the query with it.
A project from another organization is indistinguishable from a missing one.
"""

import uuid

from sqlalchemy import func
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.time import utcnow
from app.models.project import Project


async def list_projects(
    session: AsyncSession,
    organization_id: uuid.UUID,
    *,
    q: str | None = None,
    status: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[Project], int]:
    """Return one page of the organization's projects, newest first, plus the total count."""
    filters = [Project.organization_id == organization_id]
    if q:
        filters.append(col(Project.name).ilike(f"%{q}%"))
    if status:
        filters.append(Project.status == status)

    total = (
        await session.execute(select(func.count()).select_from(Project).where(*filters))
    ).one()[0]

    statement = (
        select(Project)
        .where(*filters)
        .order_by(col(Project.created_at).desc(), col(Project.id).desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    items = list((await session.execute(statement)).scalars().all())
    return items, total


async def get_project(
    session: AsyncSession, organization_id: uuid.UUID, project_id: uuid.UUID
) -> Project | None:
    statement = select(Project).where(
        Project.id == project_id, Project.organization_id == organization_id
    )
    return (await session.execute(statement)).scalar_one_or_none()


async def create_project(
    session: AsyncSession,
    organization_id: uuid.UUID,
    created_by: uuid.UUID,
    *,
    name: str,
    description: str | None = None,
    status: str = "draft",
) -> Project:
    project = Project(
        organization_id=organization_id,
        created_by=created_by,
        name=name,
        description=description,
        status=status,
    )
    session.add(project)
    await session.commit()
    await session.refresh(project)
    return project


async def update_project(
    session: AsyncSession,
    organization_id: uuid.UUID,
    project_id: uuid.UUID,
    **updates,
) -> Project | None:
    """Apply the given fields. Returns None when the project is not in this organization."""
    project = await get_project(session, organization_id, project_id)
    if project is None:
        return None

    for key, value in updates.items():
        setattr(project, key, value)
    project.updated_at = utcnow()

    session.add(project)
    await session.commit()
    await session.refresh(project)
    return project


async def delete_project(
    session: AsyncSession, organization_id: uuid.UUID, project_id: uuid.UUID
) -> bool:
    project = await get_project(session, organization_id, project_id)
    if project is None:
        return False
    await session.delete(project)
    await session.commit()
    return True
