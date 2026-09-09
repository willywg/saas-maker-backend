"""Token sessions: issue access+refresh pairs, rotate on refresh, revoke on logout.

Refresh tokens are JWTs (type="refresh") that also carry ``org_id`` (the
organization the session is scoped to) and ``jti`` (the RefreshToken row id).
Only the SHA256 of the token is stored.
"""

import uuid
from datetime import timedelta

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import settings
from app.core.time import utcnow
from app.models import Organization, RefreshToken, User
from app.services.auth_service import (
    create_access_token,
    create_token,
    decode_token,
    get_membership,
    hash_token,
    list_user_organizations,
)


async def issue_tokens(
    session: AsyncSession,
    user: User,
    organization: Organization,
    role: str,
    user_agent: str | None = None,
) -> tuple[str, str]:
    """Create an access token and a persisted refresh token for (user, organization)."""
    access_token = create_access_token(
        user_id=user.id, email=user.email, org_id=organization.id, role=role
    )

    jti = uuid.uuid4()
    expires_delta = timedelta(days=settings.refresh_token_expire_days)
    refresh_token = create_token(
        {"sub": str(user.id), "org_id": str(organization.id), "jti": str(jti)},
        expires_delta,
        "refresh",
    )
    session.add(
        RefreshToken(
            id=jti,
            user_id=user.id,
            organization_id=organization.id,
            token_hash=hash_token(refresh_token),
            user_agent=(user_agent or "")[:255] or None,
            expires_at=utcnow() + expires_delta,
        )
    )
    await session.commit()
    return access_token, refresh_token


async def _get_active_record(session: AsyncSession, raw_token: str) -> RefreshToken:
    """Decode and look up a refresh token; raises ValueError if unusable."""
    payload = decode_token(raw_token)  # raises ValueError on bad signature/expiry
    if payload.get("type") != "refresh":
        raise ValueError("Tipo de token inválido")

    statement = select(RefreshToken).where(RefreshToken.token_hash == hash_token(raw_token))
    result = await session.execute(statement)
    record = result.scalar_one_or_none()
    if not record or record.revoked_at is not None or record.expires_at < utcnow():
        raise ValueError("Token de actualización inválido o revocado")
    return record


async def rotate_tokens(
    session: AsyncSession, raw_refresh_token: str, user_agent: str | None = None
) -> tuple[User, Organization, str, str, str]:
    """
    Exchange a refresh token for a new access+refresh pair.

    The used refresh token is revoked (rotation). The session stays scoped to the
    organization stored in the token; if that membership no longer exists, it falls
    back to the user's first active organization.

    Returns (user, organization, role, access_token, refresh_token).
    """
    record = await _get_active_record(session, raw_refresh_token)

    user = await session.get(User, record.user_id)
    if not user or not user.is_active:
        raise ValueError("Usuario no encontrado o inactivo")

    membership = None
    if record.organization_id:
        membership = await get_membership(session, user.id, record.organization_id)
    if not membership:
        organizations = await list_user_organizations(session, user.id)
        membership = organizations[0] if organizations else None
    if not membership:
        raise ValueError("No se encontró una organización activa")
    organization, role = membership

    record.revoked_at = utcnow()
    session.add(record)

    access_token, refresh_token = await issue_tokens(session, user, organization, role, user_agent)
    return user, organization, role, access_token, refresh_token


async def revoke_token(session: AsyncSession, raw_refresh_token: str) -> bool:
    """Revoke one refresh token (logout). Returns False if it was not valid anyway."""
    try:
        record = await _get_active_record(session, raw_refresh_token)
    except ValueError:
        return False
    record.revoked_at = utcnow()
    session.add(record)
    await session.commit()
    return True


async def switch_organization(
    session: AsyncSession,
    user_id: uuid.UUID,
    organization_id: uuid.UUID,
    user_agent: str | None = None,
    current_refresh_token: str | None = None,
) -> tuple[Organization, str, str, str]:
    """
    Issue a new token pair scoped to another organization the user belongs to.

    Raises PermissionError if the user is not a member. The caller's previous refresh
    token is revoked when provided.

    Returns (organization, role, access_token, refresh_token).
    """
    user = await session.get(User, user_id)
    if not user or not user.is_active:
        raise ValueError("Usuario no encontrado o inactivo")

    membership = await get_membership(session, user_id, organization_id)
    if not membership:
        raise PermissionError("No perteneces a esa organización")
    organization, role = membership

    if current_refresh_token:
        await revoke_token(session, current_refresh_token)

    access_token, refresh_token = await issue_tokens(session, user, organization, role, user_agent)
    return organization, role, access_token, refresh_token
