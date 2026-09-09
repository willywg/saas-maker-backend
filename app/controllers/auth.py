"""Authentication endpoints: registration, login, sessions, email verification, multi-org."""

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import settings
from app.core.dependencies import CurrentUser
from app.core.rate_limit import auth_limit, limiter
from app.db.session import get_session
from app.models import Organization, User
from app.schemas.auth import (
    AcceptInviteRequest,
    ChangePasswordRequest,
    ForgotPasswordRequest,
    InviteInfoResponse,
    LogoutRequest,
    MessageResponse,
    RefreshRequest,
    RegisterRequest,
    ResetPasswordRequest,
    SwitchOrganizationRequest,
    TokenResponse,
    UpdateProfileRequest,
    UserOrganizationItem,
    UserResponse,
    ValidateResetTokenResponse,
    VerifyEmailRequest,
)
from app.services import auth_service, invitation_service, session_service
from app.services.email_service import (
    send_password_reset_email,
    send_verification_email,
    send_welcome_email,
)

router = APIRouter()


def _user_agent(request: Request) -> str | None:
    return request.headers.get("user-agent")


async def _queue_verification_email(
    background_tasks: BackgroundTasks, session: AsyncSession, user: User
) -> None:
    raw_token = await auth_service.create_email_verification_token(session, user.id)
    background_tasks.add_task(
        send_verification_email,
        email_to=user.email,
        user_name=user.full_name,
        verify_url=f"{settings.frontend_url}/verify-email/{raw_token}",
        expire_hours=settings.email_verification_token_expire_hours,
    )


# --- Registration & login ---


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit(auth_limit)
async def register(
    request: Request,
    payload: RegisterRequest,
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_session),
):
    """
    Register a new user and create their organization.

    Creates the user, the organization and the owner membership, sends a welcome
    email and an email-verification link, and returns a token pair.
    """
    try:
        user, organization = await auth_service.register_user(
            session=session,
            email=payload.email,
            password=payload.password,
            full_name=payload.full_name,
            org_name=payload.organization_name,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e

    access_token, refresh_token = await session_service.issue_tokens(
        session, user, organization, "owner", _user_agent(request)
    )

    background_tasks.add_task(
        send_welcome_email,
        email_to=user.email,
        user_name=user.full_name,
        organization_name=organization.name,
        dashboard_url=f"{settings.frontend_url}/dashboard",
    )
    await _queue_verification_email(background_tasks, session, user)

    return TokenResponse(access_token=access_token, refresh_token=refresh_token)


@router.post("/login", response_model=TokenResponse)
@limiter.limit(auth_limit)
async def login(
    request: Request,
    form_data: OAuth2PasswordRequestForm = Depends(),
    session: AsyncSession = Depends(get_session),
):
    """
    Authenticate a user and return JWT tokens.

    For Swagger UI: username = email, password = password.
    The session is scoped to the user's first organization; use
    ``POST /auth/switch-organization`` to change it.
    """
    result = await auth_service.authenticate_user(
        session=session,
        email=form_data.username,  # OAuth2 uses 'username' field, we treat it as email
        password=form_data.password,
    )
    if not result:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Email o contraseña incorrectos",
            headers={"WWW-Authenticate": "Bearer"},
        )
    user, organization, role = result

    if settings.require_email_verification and not user.email_verified:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Debes confirmar tu correo antes de iniciar sesión",
        )

    access_token, refresh_token = await session_service.issue_tokens(
        session, user, organization, role, _user_agent(request)
    )
    return TokenResponse(access_token=access_token, refresh_token=refresh_token)


@router.post("/refresh", response_model=TokenResponse)
async def refresh(
    request: Request,
    payload: RefreshRequest,
    session: AsyncSession = Depends(get_session),
):
    """
    Exchange a refresh token for a new access+refresh pair.

    The refresh token is rotated: the one sent is revoked and cannot be reused.
    """
    try:
        _, _, _, access_token, refresh_token = await session_service.rotate_tokens(
            session, payload.refresh_token, _user_agent(request)
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e)) from None
    return TokenResponse(access_token=access_token, refresh_token=refresh_token)


@router.post("/logout", response_model=MessageResponse)
async def logout(
    payload: LogoutRequest,
    session: AsyncSession = Depends(get_session),
):
    """Revoke a refresh token (logout of this device). Always returns 200."""
    await session_service.revoke_token(session, payload.refresh_token)
    return MessageResponse(message="Sesión cerrada")


@router.post("/logout-all", response_model=MessageResponse)
async def logout_all(
    user: CurrentUser,
    session: AsyncSession = Depends(get_session),
):
    """Revoke every refresh token of the current user (logout of all devices)."""
    count = await auth_service.revoke_all_sessions(session, user.user_id)
    await session.commit()
    return MessageResponse(message=f"Se cerraron {count} sesiones")


# --- Current user ---


@router.get("/me", response_model=UserResponse)
async def get_current_user_info(
    user: CurrentUser,
    session: AsyncSession = Depends(get_session),
):
    """Get current authenticated user information."""
    user_obj = await session.get(User, user.user_id)
    if not user_obj:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Usuario no encontrado")

    organization = await session.get(Organization, user.organization_id)
    if not organization:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Organización no encontrada"
        )

    return UserResponse(
        id=str(user.user_id),
        email=user.email,
        full_name=user_obj.full_name,
        email_verified=user_obj.email_verified,
        organization_id=str(user.organization_id),
        organization_name=organization.name,
        role=user.role,
    )


@router.put("/me", response_model=UserResponse)
async def update_profile(
    payload: UpdateProfileRequest,
    user: CurrentUser,
    session: AsyncSession = Depends(get_session),
):
    """Update the current user's profile."""
    try:
        user_obj = await auth_service.update_user_profile(
            session, user.user_id, full_name=payload.full_name
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e

    organization = await session.get(Organization, user.organization_id)
    return UserResponse(
        id=str(user.user_id),
        email=user.email,
        full_name=user_obj.full_name,
        email_verified=user_obj.email_verified,
        organization_id=str(user.organization_id),
        organization_name=organization.name if organization else "",
        role=user.role,
    )


@router.post("/change-password", response_model=MessageResponse)
async def change_password(
    payload: ChangePasswordRequest,
    user: CurrentUser,
    session: AsyncSession = Depends(get_session),
):
    """
    Change the current user's password.

    Every other session is revoked. Send your own ``refresh_token`` to keep this one.
    """
    try:
        await auth_service.change_user_password(
            session,
            user.user_id,
            current_password=payload.current_password,
            new_password=payload.new_password,
            keep_refresh_token=payload.refresh_token,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    return MessageResponse(message="Contraseña actualizada")


# --- Organizations (multi-tenant membership) ---


@router.get("/organizations", response_model=list[UserOrganizationItem])
async def list_my_organizations(
    user: CurrentUser,
    session: AsyncSession = Depends(get_session),
):
    """Organizations the current user belongs to; ``is_current`` marks the session's org."""
    organizations = await auth_service.list_user_organizations(session, user.user_id)
    return [
        UserOrganizationItem(
            id=str(org.id),
            name=org.name,
            slug=org.slug,
            role=role,
            is_current=org.id == user.organization_id,
        )
        for org, role in organizations
    ]


@router.post("/switch-organization", response_model=TokenResponse)
async def switch_organization(
    request: Request,
    payload: SwitchOrganizationRequest,
    user: CurrentUser,
    session: AsyncSession = Depends(get_session),
):
    """Get a new token pair scoped to another organization the user belongs to."""
    try:
        _, _, access_token, refresh_token = await session_service.switch_organization(
            session,
            user.user_id,
            payload.organization_id,
            user_agent=_user_agent(request),
            current_refresh_token=payload.refresh_token,
        )
    except PermissionError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e)) from e
    return TokenResponse(access_token=access_token, refresh_token=refresh_token)


# --- Email verification ---


@router.post("/verify-email", response_model=MessageResponse)
@limiter.limit(auth_limit)
async def verify_email(
    request: Request,
    payload: VerifyEmailRequest,
    session: AsyncSession = Depends(get_session),
):
    """Confirm an email address using the token from the verification link."""
    user = await auth_service.verify_email_with_token(session, payload.token)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Enlace de verificación inválido o expirado",
        )
    return MessageResponse(message="Correo confirmado")


@router.post("/resend-verification", response_model=MessageResponse)
@limiter.limit(auth_limit)
async def resend_verification(
    request: Request,
    background_tasks: BackgroundTasks,
    user: CurrentUser,
    session: AsyncSession = Depends(get_session),
):
    """Send a new verification link to the current user."""
    user_obj = await session.get(User, user.user_id)
    if not user_obj:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Usuario no encontrado")
    if user_obj.email_verified:
        return MessageResponse(message="Tu correo ya está confirmado")

    await _queue_verification_email(background_tasks, session, user_obj)
    return MessageResponse(message="Te enviamos un nuevo enlace de confirmación")


# --- Invitations ---


@router.get("/invite/{token}", response_model=InviteInfoResponse)
async def get_invite_info(
    token: str,
    session: AsyncSession = Depends(get_session),
):
    """Public information about an invitation, to validate it before showing the form."""
    try:
        invite_info = await invitation_service.get_invite_info(session, token)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    return InviteInfoResponse(**invite_info)


@router.post("/accept-invite", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit(auth_limit)
async def accept_invite(
    request: Request,
    payload: AcceptInviteRequest,
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_session),
):
    """
    Accept an invitation: creates the account (or adds the membership to an
    existing one) and returns tokens scoped to the inviting organization.
    """
    try:
        user, organization, role = await invitation_service.accept_invitation(
            session=session,
            token=payload.token,
            full_name=payload.full_name,
            password=payload.password,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e

    access_token, refresh_token = await session_service.issue_tokens(
        session, user, organization, role, _user_agent(request)
    )

    background_tasks.add_task(
        send_welcome_email,
        email_to=user.email,
        user_name=user.full_name,
        organization_name=organization.name,
        dashboard_url=f"{settings.frontend_url}/dashboard",
    )
    return TokenResponse(access_token=access_token, refresh_token=refresh_token)


# --- Password reset ---


@router.post("/forgot-password", response_model=MessageResponse)
@limiter.limit(auth_limit)
async def forgot_password(
    request: Request,
    payload: ForgotPasswordRequest,
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_session),
):
    """Request password reset. Always returns 200 (no email enumeration)."""
    result = await auth_service.create_password_reset_token(session, payload.email)
    if result:
        raw_token, user_name = result
        background_tasks.add_task(
            send_password_reset_email,
            email_to=payload.email,
            user_name=user_name,
            reset_url=f"{settings.frontend_url}/reset-password/{raw_token}",
            expire_minutes=settings.password_reset_token_expire_minutes,
        )
    return MessageResponse(message="Si el email existe, recibirás un correo con instrucciones")


@router.get("/reset-password/{token}", response_model=ValidateResetTokenResponse)
async def validate_reset_token(
    token: str,
    session: AsyncSession = Depends(get_session),
):
    """Validate a reset token and return the masked email."""
    result = await auth_service.validate_password_reset_token(session, token)
    if not result:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Enlace inválido o expirado"
        )
    _, masked_email = result
    return ValidateResetTokenResponse(email=masked_email)


@router.post("/reset-password", response_model=MessageResponse)
@limiter.limit(auth_limit)
async def reset_password(
    request: Request,
    payload: ResetPasswordRequest,
    session: AsyncSession = Depends(get_session),
):
    """Set a new password using a reset token. Revokes every existing session."""
    ok = await auth_service.reset_password_with_token(session, payload.token, payload.new_password)
    if not ok:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Enlace inválido o expirado"
        )
    return MessageResponse(message="Contraseña restablecida")
