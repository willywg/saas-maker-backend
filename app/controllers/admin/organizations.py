"""Admin organization management endpoints."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.dependencies import CurrentAdmin
from app.db.session import get_session
from app.schemas.admin import (
    OrganizationDetailAdmin,
    OrganizationListItem,
    OrganizationUpdateAdmin,
    PaginatedResponse,
    StatusToggleRequest,
    UserListItem,
)
from app.services.admin_service import (
    deactivate_organization,
    get_organization,
    list_organization_users,
    list_organizations,
    toggle_organization_status,
    update_organization,
)

router = APIRouter()


@router.get("", response_model=PaginatedResponse[OrganizationListItem])
async def list_all_organizations(
    current_admin: CurrentAdmin,
    session: AsyncSession = Depends(get_session),
    page: int = Query(1, ge=1, description="Número de página"),
    page_size: int = Query(20, ge=1, le=100, description="Elementos por página"),
    search: str | None = Query(None, description="Buscar por nombre o slug"),
    is_active: bool | None = Query(None, description="Filtrar por estado activo"),
    sort_by: str = Query("created_at", description="Campo para ordenar"),
    sort_order: str = Query("desc", pattern="^(asc|desc)$", description="Orden"),
):
    """
    List all organizations with pagination and filters.

    Requires admin authentication.
    """
    return await list_organizations(
        session=session,
        page=page,
        page_size=page_size,
        search=search,
        is_active=is_active,
        sort_by=sort_by,
        sort_order=sort_order,
    )


@router.get("/{org_id}", response_model=OrganizationDetailAdmin)
async def get_organization_detail(
    org_id: uuid.UUID,
    current_admin: CurrentAdmin,
    session: AsyncSession = Depends(get_session),
):
    """
    Get organization details including members.

    Requires admin authentication.
    """
    org = await get_organization(session, org_id)

    if not org:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Organización no encontrada",
        )

    return org


@router.put("/{org_id}", response_model=OrganizationDetailAdmin)
async def update_organization_admin(
    org_id: uuid.UUID,
    data: OrganizationUpdateAdmin,
    current_admin: CurrentAdmin,
    session: AsyncSession = Depends(get_session),
):
    """
    Update an organization.

    Requires admin authentication.
    """
    org = await update_organization(session, org_id, data)

    if not org:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Organización no encontrada",
        )

    # Return full detail
    return await get_organization(session, org_id)


@router.patch("/{org_id}/status", response_model=OrganizationDetailAdmin)
async def toggle_organization_status_admin(
    org_id: uuid.UUID,
    data: StatusToggleRequest,
    current_admin: CurrentAdmin,
    session: AsyncSession = Depends(get_session),
):
    """
    Toggle organization active status.

    Requires admin authentication.
    """
    org = await toggle_organization_status(session, org_id, data.is_active)

    if not org:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Organización no encontrada",
        )

    return await get_organization(session, org_id)


@router.get("/{org_id}/users", response_model=PaginatedResponse[UserListItem])
async def list_organization_users_admin(
    org_id: uuid.UUID,
    current_admin: CurrentAdmin,
    session: AsyncSession = Depends(get_session),
    page: int = Query(1, ge=1, description="Número de página"),
    limit: int = Query(10, ge=1, le=100, description="Elementos por página"),
):
    """
    List users in an organization.

    Requires admin authentication.
    """
    # Check org exists
    org = await get_organization(session, org_id)
    if not org:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Organización no encontrada",
        )

    return await list_organization_users(session, org_id, page, limit)


@router.delete("/{org_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_organization_admin(
    org_id: uuid.UUID,
    current_admin: CurrentAdmin,
    session: AsyncSession = Depends(get_session),
):
    """
    Deactivate an organization (soft delete).

    Sets is_active=False instead of actually deleting.
    Requires admin authentication.
    """
    success = await deactivate_organization(session, org_id)

    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Organización no encontrada",
        )

    return None
