"""Organization management service."""

import uuid

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.time import utcnow
from app.models.tenant import InviteToken, Organization, OrganizationMember, User
from app.services import invitation_service


async def get_organization(
    session: AsyncSession, organization_id: uuid.UUID
) -> Organization | None:
    """Get organization by ID."""
    return await session.get(Organization, organization_id)


async def update_organization(
    session: AsyncSession, organization_id: uuid.UUID, **updates
) -> Organization:
    """Update organization details."""
    organization = await session.get(Organization, organization_id)
    if not organization:
        raise ValueError("Organización no encontrada")

    for key, value in updates.items():
        if hasattr(organization, key) and value is not None:
            setattr(organization, key, value)

    organization.updated_at = utcnow()

    session.add(organization)
    await session.commit()
    await session.refresh(organization)
    return organization


async def list_members(session: AsyncSession, organization_id: uuid.UUID) -> list[tuple[User, str]]:
    """
    List all members of an organization with their roles.

    Returns: List of (User, role) tuples
    """
    statement = (
        select(User, OrganizationMember.role)
        .join(OrganizationMember, User.id == OrganizationMember.user_id)
        .where(OrganizationMember.organization_id == organization_id)
        .order_by(OrganizationMember.created_at)
    )
    result = await session.execute(statement)
    return list(result.all())


async def invite_member(
    session: AsyncSession,
    organization_id: uuid.UUID,
    email: str,
    role: str,
    invited_by: uuid.UUID,
) -> InviteToken:
    """
    Invite a new member to the organization.

    Creates an invitation token that the user can use to join.
    The token can be shared via any channel (email, WhatsApp, etc).

    Args:
        organization_id: Organization to invite to
        email: Email of person to invite
        role: Role to assign ("admin" or "member", not "owner")
        invited_by: User ID of person sending invitation

    Returns: InviteToken with shareable token

    Raises:
        ValueError: If user is already a member or invalid role
    """
    return await invitation_service.create_invite_token(
        session=session,
        organization_id=organization_id,
        email=email,
        role=role,
        created_by=invited_by,
    )


async def remove_member(
    session: AsyncSession,
    organization_id: uuid.UUID,
    user_id: uuid.UUID,
    removed_by: uuid.UUID,
) -> bool:
    """
    Remove a member from the organization.

    Args:
        organization_id: Organization to remove from
        user_id: User to remove
        removed_by: User performing the removal

    Returns: True if removed, False if not found

    Raises:
        ValueError: If trying to remove the last owner or yourself
    """
    # Can't remove yourself
    if user_id == removed_by:
        raise ValueError("No puedes eliminarte a ti mismo. Transfiere la propiedad primero.")

    # Get membership
    statement = (
        select(OrganizationMember)
        .where(OrganizationMember.organization_id == organization_id)
        .where(OrganizationMember.user_id == user_id)
    )
    result = await session.execute(statement)
    membership = result.scalars().first()

    if not membership:
        return False

    # If removing an owner, ensure there's at least one other owner
    if membership.role == "owner":
        statement = (
            select(OrganizationMember)
            .where(OrganizationMember.organization_id == organization_id)
            .where(OrganizationMember.role == "owner")
        )
        result = await session.execute(statement)
        owners = list(result.scalars().all())

        if len(owners) <= 1:
            raise ValueError(
                "No puedes eliminar al último propietario. Promueve a otro miembro primero."
            )

    # Delete membership (not the user)
    await session.delete(membership)
    await session.commit()
    return True


async def change_member_role(
    session: AsyncSession,
    organization_id: uuid.UUID,
    user_id: uuid.UUID,
    new_role: str,
) -> OrganizationMember:
    """
    Change a member's role.

    Args:
        organization_id: Organization
        user_id: User whose role to change
        new_role: New role ("owner", "admin", or "member")

    Returns: Updated membership

    Raises:
        ValueError: If removing the last owner or invalid role
    """
    if new_role not in ["owner", "admin", "member"]:
        raise ValueError("Rol inválido")

    # Get membership
    statement = (
        select(OrganizationMember)
        .where(OrganizationMember.organization_id == organization_id)
        .where(OrganizationMember.user_id == user_id)
    )
    result = await session.execute(statement)
    membership = result.scalars().first()

    if not membership:
        raise ValueError("Miembro no encontrado")

    # If demoting an owner, ensure there's another owner
    if membership.role == "owner" and new_role != "owner":
        statement = (
            select(OrganizationMember)
            .where(OrganizationMember.organization_id == organization_id)
            .where(OrganizationMember.role == "owner")
        )
        result = await session.execute(statement)
        owners = list(result.scalars().all())

        if len(owners) <= 1:
            raise ValueError(
                "No puedes degradar al último propietario. Promueve a otro miembro primero."
            )

    membership.role = new_role
    session.add(membership)
    await session.commit()
    await session.refresh(membership)

    return membership


async def count_owners(session: AsyncSession, organization_id: uuid.UUID) -> int:
    """Count number of owners in an organization."""
    statement = (
        select(OrganizationMember)
        .where(OrganizationMember.organization_id == organization_id)
        .where(OrganizationMember.role == "owner")
    )
    result = await session.execute(statement)
    return len(list(result.scalars().all()))
