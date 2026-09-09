"""Admin user management endpoints."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.dependencies import CurrentAdmin
from app.db.session import get_session
from app.schemas.admin import (
    PaginatedResponse,
    StatusToggleRequest,
    UserDetailAdmin,
    UserListItem,
    UserUpdateAdmin,
)
from app.services.admin_service import (
    deactivate_user,
    get_dashboard_stats,
    get_user,
    list_users,
    toggle_user_status,
    update_user,
)

router = APIRouter()


@router.get("/stats")
async def get_stats(
    current_admin: CurrentAdmin,
    session: AsyncSession = Depends(get_session),
):
    """
    Get dashboard statistics.

    Returns counts for organizations and users.
    Requires admin authentication.
    """
    return await get_dashboard_stats(session)


@router.get("", response_model=PaginatedResponse[UserListItem])
async def list_all_users(
    current_admin: CurrentAdmin,
    session: AsyncSession = Depends(get_session),
    page: int = Query(1, ge=1, description="Número de página"),
    page_size: int = Query(20, ge=1, le=100, description="Elementos por página"),
    search: str | None = Query(None, description="Buscar por email o nombre"),
    is_active: bool | None = Query(None, description="Filtrar por estado activo"),
    organization_id: uuid.UUID | None = Query(None, description="Filtrar por organización"),
    sort_by: str = Query("created_at", description="Campo para ordenar"),
    sort_order: str = Query("desc", pattern="^(asc|desc)$", description="Orden"),
):
    """
    List all users with pagination and filters.

    Requires admin authentication.
    """
    return await list_users(
        session=session,
        page=page,
        page_size=page_size,
        search=search,
        is_active=is_active,
        organization_id=organization_id,
        sort_by=sort_by,
        sort_order=sort_order,
    )


@router.get("/{user_id}", response_model=UserDetailAdmin)
async def get_user_detail(
    user_id: uuid.UUID,
    current_admin: CurrentAdmin,
    session: AsyncSession = Depends(get_session),
):
    """
    Get user details including memberships.

    Requires admin authentication.
    """
    user = await get_user(session, user_id)

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Usuario no encontrado",
        )

    return user


@router.put("/{user_id}", response_model=UserDetailAdmin)
async def update_user_admin(
    user_id: uuid.UUID,
    data: UserUpdateAdmin,
    current_admin: CurrentAdmin,
    session: AsyncSession = Depends(get_session),
):
    """
    Update a user.

    Requires admin authentication.
    """
    user = await update_user(session, user_id, data)

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Usuario no encontrado",
        )

    # Return full detail
    return await get_user(session, user_id)


@router.patch("/{user_id}/status", response_model=UserDetailAdmin)
async def toggle_user_status_admin(
    user_id: uuid.UUID,
    data: StatusToggleRequest,
    current_admin: CurrentAdmin,
    session: AsyncSession = Depends(get_session),
):
    """
    Toggle user active status.

    Requires admin authentication.
    """
    user = await toggle_user_status(session, user_id, data.is_active)

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Usuario no encontrado",
        )

    return await get_user(session, user_id)


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user_admin(
    user_id: uuid.UUID,
    current_admin: CurrentAdmin,
    session: AsyncSession = Depends(get_session),
):
    """
    Deactivate a user (soft delete).

    Sets is_active=False instead of actually deleting.
    Requires admin authentication.
    """
    success = await deactivate_user(session, user_id)

    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Usuario no encontrado",
        )

    return None
