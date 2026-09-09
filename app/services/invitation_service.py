"""Invitation service for managing organization invitations."""

import uuid
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.time import utcnow
from app.models import InviteToken, Organization, OrganizationMember, User
from app.services.auth_service import hash_password


async def create_invite_token(
    session: AsyncSession,
    organization_id: uuid.UUID,
    email: str,
    role: str,
    created_by: uuid.UUID,
) -> InviteToken:
    """
    Create a new invitation token.

    Args:
        session: Database session
        organization_id: Organization to invite to
        email: Email of person to invite
        role: Role to assign ("admin" or "member", not "owner")
        created_by: User ID of person sending invitation

    Returns:
        InviteToken with generated token

    Raises:
        ValueError: If role is invalid or user is already a member
    """
    # Validate role (can't invite as owner)
    if role not in ["admin", "member"]:
        raise ValueError("Solo puedes invitar como 'admin' o 'member'")

    email = email.lower().strip()

    # Check if user already exists and is member
    user_stmt = select(User).where(User.email == email)
    user_result = await session.execute(user_stmt)
    existing_user = user_result.scalars().first()

    if existing_user:
        member_stmt = select(OrganizationMember).where(
            OrganizationMember.user_id == existing_user.id,
            OrganizationMember.organization_id == organization_id,
        )
        member_result = await session.execute(member_stmt)
        if member_result.scalars().first():
            raise ValueError("El usuario ya es miembro de esta organización")

    # Invalidate any existing pending invites for this email+org
    existing_invite_stmt = select(InviteToken).where(
        InviteToken.email == email,
        InviteToken.organization_id == organization_id,
        InviteToken.accepted_at == None,
    )
    existing_result = await session.execute(existing_invite_stmt)
    for old_invite in existing_result.scalars().all():
        await session.delete(old_invite)

    # Create new invite token
    invite = InviteToken(
        organization_id=organization_id,
        email=email,
        role=role,
        token=InviteToken.generate_token(),
        expires_at=utcnow() + timedelta(days=settings.invite_token_expire_days),
        created_by=created_by,
    )
    session.add(invite)
    await session.flush()
    await session.refresh(invite)

    return invite


async def get_invite_info(
    session: AsyncSession,
    token: str,
) -> dict:
    """
    Get invitation info for display (public endpoint).

    Args:
        session: Database session
        token: Invitation token

    Returns:
        Dictionary with email, organization_name, role, invited_by_name, expires_at

    Raises:
        ValueError: If token is invalid, expired, or already used
    """
    stmt = select(InviteToken).where(InviteToken.token == token)
    result = await session.execute(stmt)
    invite = result.scalars().first()

    if not invite:
        raise ValueError("Invitación inválida")

    if invite.accepted_at is not None:
        raise ValueError("Esta invitación ya fue utilizada")

    if invite.expires_at < utcnow():
        raise ValueError("Esta invitación ha expirado")

    # Get organization info
    org_stmt = select(Organization).where(Organization.id == invite.organization_id)
    org_result = await session.execute(org_stmt)
    organization = org_result.scalars().first()

    # Get inviter info
    inviter_stmt = select(User).where(User.id == invite.created_by)
    inviter_result = await session.execute(inviter_stmt)
    inviter = inviter_result.scalars().first()

    return {
        "email": invite.email,
        "organization_name": organization.name if organization else "Unknown",
        "role": invite.role,
        "invited_by_name": inviter.full_name or inviter.email if inviter else "Unknown",
        "expires_at": invite.expires_at,
    }


async def accept_invitation(
    session: AsyncSession,
    token: str,
    full_name: str,
    password: str,
) -> tuple[User, Organization, str]:
    """
    Accept invitation and create user account.

    Args:
        session: Database session
        token: Invitation token
        full_name: Full name for the new user
        password: Password for the new user

    Returns:
        Tuple of (User, Organization, role)

    Raises:
        ValueError: If token is invalid, expired, or already used
    """
    # Validate token
    stmt = select(InviteToken).where(InviteToken.token == token)
    result = await session.execute(stmt)
    invite = result.scalars().first()

    if not invite:
        raise ValueError("Invitación inválida")

    if invite.accepted_at is not None:
        raise ValueError("Esta invitación ya fue utilizada")

    if invite.expires_at < utcnow():
        raise ValueError("Esta invitación ha expirado")

    # Check if user already exists
    user_stmt = select(User).where(User.email == invite.email)
    user_result = await session.execute(user_stmt)
    user = user_result.scalars().first()

    if not user:
        # Create new user
        user = User(
            email=invite.email,
            password_hash=hash_password(password),
            full_name=full_name,
            is_active=True,
            email_verified=True,  # Verified via invite link
        )
        session.add(user)
        await session.flush()
    else:
        # User exists - verify they're not already a member
        member_stmt = select(OrganizationMember).where(
            OrganizationMember.user_id == user.id,
            OrganizationMember.organization_id == invite.organization_id,
        )
        member_result = await session.execute(member_stmt)
        if member_result.scalars().first():
            raise ValueError("El usuario ya es miembro de esta organización")

        # Update user info (user accepting invite should set their credentials)
        user.full_name = full_name
        user.password_hash = hash_password(password)
        session.add(user)

    # Create membership
    membership = OrganizationMember(
        organization_id=invite.organization_id,
        user_id=user.id,
        role=invite.role,
    )
    session.add(membership)

    # Mark invite as used
    invite.accepted_at = utcnow()

    await session.flush()

    # Get organization for response
    org_stmt = select(Organization).where(Organization.id == invite.organization_id)
    org_result = await session.execute(org_stmt)
    organization = org_result.scalars().first()

    await session.commit()

    return user, organization, invite.role


def build_invite_url(token: str) -> str:
    """Build the full invitation URL for frontend."""
    return f"{settings.frontend_url}/invite/{token}"
