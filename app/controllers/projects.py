"""Project endpoints (reference tenant-scoped resource).

Read: any member of the organization. Write: admin or owner.
Anything outside the caller's organization answers 404, never 403,
so the API does not reveal whether the resource exists.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.dependencies import CurrentUser, require_role
from app.db.session import get_session
from app.models.project import Project
from app.schemas.project import (
    ProjectCreate,
    ProjectListResponse,
    ProjectResponse,
    ProjectStatus,
    ProjectUpdate,
)
from app.services import project_service

router = APIRouter()

NOT_FOUND = HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Proyecto no encontrado")


def _to_response(project: Project) -> ProjectResponse:
    return ProjectResponse(
        id=str(project.id),
        name=project.name,
        description=project.description,
        status=project.status,  # type: ignore[arg-type]
        created_by=str(project.created_by) if project.created_by else None,
        created_at=project.created_at,
        updated_at=project.updated_at,
    )


@router.get("", response_model=ProjectListResponse)
async def list_projects(
    user: CurrentUser,
    session: AsyncSession = Depends(get_session),
    q: str | None = Query(None, max_length=100, description="Filtro por nombre"),
    status: ProjectStatus | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    """List the organization's projects. Requires: any member."""
    items, total = await project_service.list_projects(
        session, user.organization_id, q=q, status=status, page=page, page_size=page_size
    )
    return ProjectListResponse(
        items=[_to_response(p) for p in items], total=total, page=page, page_size=page_size
    )


@router.get("/{project_id}", response_model=ProjectResponse)
async def get_project(
    project_id: uuid.UUID,
    user: CurrentUser,
    session: AsyncSession = Depends(get_session),
):
    """Get one project. Requires: any member."""
    project = await project_service.get_project(session, user.organization_id, project_id)
    if project is None:
        raise NOT_FOUND
    return _to_response(project)


@router.post(
    "",
    response_model=ProjectResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_role("admin"))],
)
async def create_project(
    request: ProjectCreate,
    user: CurrentUser,
    session: AsyncSession = Depends(get_session),
):
    """Create a project. Requires: admin or owner."""
    project = await project_service.create_project(
        session, user.organization_id, user.user_id, **request.model_dump()
    )
    return _to_response(project)


@router.put(
    "/{project_id}",
    response_model=ProjectResponse,
    dependencies=[Depends(require_role("admin"))],
)
async def update_project(
    project_id: uuid.UUID,
    request: ProjectUpdate,
    user: CurrentUser,
    session: AsyncSession = Depends(get_session),
):
    """Update a project. Requires: admin or owner."""
    project = await project_service.update_project(
        session, user.organization_id, project_id, **request.model_dump(exclude_unset=True)
    )
    if project is None:
        raise NOT_FOUND
    return _to_response(project)


@router.delete(
    "/{project_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_role("admin"))],
)
async def delete_project(
    project_id: uuid.UUID,
    user: CurrentUser,
    session: AsyncSession = Depends(get_session),
):
    """Delete a project. Requires: admin or owner."""
    if not await project_service.delete_project(session, user.organization_id, project_id):
        raise NOT_FOUND
