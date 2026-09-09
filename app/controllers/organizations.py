"""Organization management endpoints."""

import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.dependencies import CurrentUser, require_role
from app.db.session import get_session
from app.models.tenant import User
from app.schemas.organization import (
    ChangeRoleRequest,
    InviteMemberRequest,
    InviteResponse,
    MemberResponse,
    OrganizationResponse,
    OrganizationUpdate,
)
from app.services import organization_service
from app.services.email_service import send_invitation_email
from app.services.invitation_service import build_invite_url

router = APIRouter()


@router.get("/me", response_model=OrganizationResponse)
async def get_my_organization(
    user: CurrentUser,
    session: AsyncSession = Depends(get_session),
):
    """
    Get current user's organization details.

    Requires: Any authenticated user (member, admin, or owner)
    """
    organization = await organization_service.get_organization(session, user.organization_id)

    if not organization:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Organización no encontrada",
        )

    return OrganizationResponse(
        id=str(organization.id),
        name=organization.name,
        slug=organization.slug,
        is_active=organization.is_active,
        created_at=organization.created_at,
        updated_at=organization.updated_at,
    )


@router.put(
    "/me",
    response_model=OrganizationResponse,
    dependencies=[Depends(require_role("owner"))],
)
async def update_my_organization(
    request: OrganizationUpdate,
    user: CurrentUser,
    session: AsyncSession = Depends(get_session),
):
    """
    Update organization details.

    Requires: owner role
    """
    try:
        organization = await organization_service.update_organization(
            session,
            user.organization_id,
            **request.model_dump(exclude_unset=True),
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        ) from e

    return OrganizationResponse(
        id=str(organization.id),
        name=organization.name,
        slug=organization.slug,
        is_active=organization.is_active,
        created_at=organization.created_at,
        updated_at=organization.updated_at,
    )


@router.get(
    "/members",
    response_model=list[MemberResponse],
    dependencies=[Depends(require_role("admin"))],
)
async def list_organization_members(
    user: CurrentUser,
    session: AsyncSession = Depends(get_session),
):
    """
    List all members of the organization.

    Requires: admin or owner role
    """
    members = await organization_service.list_members(session, user.organization_id)

    return [
        MemberResponse(
            id=str(member.id),
            email=member.email,
            full_name=member.full_name,
            role=role,
            is_active=member.is_active,
            joined_at=member.created_at,
        )
        for member, role in members
    ]


@router.post(
    "/members/invite",
    response_model=InviteResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_role("admin"))],
)
async def invite_member(
    request: InviteMemberRequest,
    background_tasks: BackgroundTasks,
    user: CurrentUser,
    session: AsyncSession = Depends(get_session),
):
    """
    Invite a new member to the organization.

    Creates an invitation token that can be shared with the user.
    The token can only be used once and expires after 7 days.

    Sends an invitation email automatically and also returns a shareable URL
    that the admin can send via any other channel (WhatsApp, Slack, etc).

    Requires: admin or owner role
    """
    try:
        invite_token = await organization_service.invite_member(
            session=session,
            organization_id=user.organization_id,
            email=request.email,
            role=request.role,
            invited_by=user.user_id,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        ) from e

    # Get inviter and organization info for email
    inviter = await session.get(User, user.user_id)
    organization = await organization_service.get_organization(session, user.organization_id)

    invite_url = build_invite_url(invite_token.token)

    # Send invitation email in background
    background_tasks.add_task(
        send_invitation_email,
        email_to=invite_token.email,
        organization_name=organization.name if organization else "Organización",
        inviter_name=inviter.full_name or inviter.email if inviter else "Un administrador",
        role=invite_token.role,
        invite_url=invite_url,
        expires_at=invite_token.expires_at.strftime("%d/%m/%Y a las %H:%M"),
    )

    return InviteResponse(
        invite_url=invite_url,
        token=invite_token.token,
        email=invite_token.email,
        role=invite_token.role,
        expires_at=invite_token.expires_at,
    )


@router.put(
    "/members/{user_id}/role",
    response_model=MemberResponse,
    dependencies=[Depends(require_role("owner"))],
)
async def change_member_role(
    user_id: uuid.UUID,
    request: ChangeRoleRequest,
    user: CurrentUser,
    session: AsyncSession = Depends(get_session),
):
    """
    Change a member's role.

    Requires: owner role
    """
    try:
        membership = await organization_service.change_member_role(
            session=session,
            organization_id=user.organization_id,
            user_id=user_id,
            new_role=request.role,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        ) from e

    # Get user details
    member_user = await session.get(User, user_id)
    if not member_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Usuario no encontrado",
        )

    return MemberResponse(
        id=str(member_user.id),
        email=member_user.email,
        full_name=member_user.full_name,
        role=membership.role,
        is_active=member_user.is_active,
        joined_at=membership.created_at,
    )


@router.delete(
    "/members/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_role("owner"))],
)
async def remove_member(
    user_id: uuid.UUID,
    user: CurrentUser,
    session: AsyncSession = Depends(get_session),
):
    """
    Remove a member from the organization.

    Cannot remove yourself or the last owner.

    Requires: owner role
    """
    try:
        removed = await organization_service.remove_member(
            session=session,
            organization_id=user.organization_id,
            user_id=user_id,
            removed_by=user.user_id,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        ) from e

    if not removed:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Miembro no encontrado",
        )
