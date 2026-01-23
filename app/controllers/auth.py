"""Authentication endpoints for user registration, login, and token management."""

import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.dependencies import CurrentUser
from app.db.session import get_session
from app.models import Organization, OrganizationMember, User
from app.schemas.auth import (
    AcceptInviteRequest,
    InviteInfoResponse,
    RefreshRequest,
    RegisterRequest,
    TokenResponse,
    UserResponse,
)
from app.core.config import settings
from app.services import auth_service, invitation_service
from app.services.email_service import send_welcome_email

router = APIRouter()


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def register(
    request: RegisterRequest,
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_session),
):
    """
    Register a new user and create their organization.

    Automatically creates:
    - User account
    - Organization
    - Organization membership (user as owner)
    """
    try:
        user, organization = await auth_service.register_user(
            session=session,
            email=request.email,
            password=request.password,
            full_name=request.full_name,
            org_name=request.organization_name,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )

    # Generate tokens
    access_token = auth_service.create_access_token(
        user_id=user.id,
        email=user.email,
        org_id=organization.id,
        role="owner",
    )
    refresh_token = auth_service.create_refresh_token(user_id=user.id)

    # Send welcome email in background
    background_tasks.add_task(
        send_welcome_email,
        email_to=user.email,
        user_name=user.full_name,
        organization_name=organization.name,
        dashboard_url=f"{settings.frontend_url}/dashboard",
    )

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
    )


@router.post("/login", response_model=TokenResponse)
async def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    session: AsyncSession = Depends(get_session),
):
    """
    Authenticate a user and return JWT tokens.

    For Swagger UI: username = email, password = password
    For API clients: Can also send JSON with {email, password}
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

    # Generate tokens
    access_token = auth_service.create_access_token(
        user_id=user.id,
        email=user.email,
        org_id=organization.id,
        role=role,
    )
    refresh_token = auth_service.create_refresh_token(user_id=user.id)

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh(
    request: RefreshRequest,
    session: AsyncSession = Depends(get_session),
):
    """
    Get a new access token using a refresh token.
    """
    try:
        payload = auth_service.decode_token(request.refresh_token)

        # Verify it's a refresh token
        if payload.get("type") != "refresh":
            raise ValueError("Tipo de token inválido")

        user_id = payload.get("sub")
        if not user_id:
            raise ValueError("Token inválido")

    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token de actualización inválido",
        )

    # Get user and re-authenticate (to get fresh org/role data)
    statement = select(User).where(User.id == uuid.UUID(user_id))
    result = await session.execute(statement)
    user = result.scalar_one_or_none()

    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Usuario no encontrado o inactivo",
        )

    # Get organization
    statement = (
        select(Organization, OrganizationMember.role)
        .join(OrganizationMember, Organization.id == OrganizationMember.organization_id)
        .where(OrganizationMember.user_id == user.id)
        .where(Organization.is_active == True)
    )
    result = await session.execute(statement)
    org_data = result.first()

    if not org_data:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="No se encontró una organización activa",
        )

    organization, role = org_data

    # Generate new tokens
    access_token = auth_service.create_access_token(
        user_id=user.id,
        email=user.email,
        org_id=organization.id,
        role=role,
    )
    new_refresh_token = auth_service.create_refresh_token(user_id=user.id)

    return TokenResponse(
        access_token=access_token,
        refresh_token=new_refresh_token,
    )


@router.get("/me", response_model=UserResponse)
async def get_current_user_info(
    user: CurrentUser,
    session: AsyncSession = Depends(get_session),
):
    """
    Get current authenticated user information.

    Requires: Valid access token
    """
    # Get user details
    statement = select(User).where(User.id == user.user_id)
    result = await session.execute(statement)
    user_obj = result.scalar_one_or_none()

    if not user_obj:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Usuario no encontrado",
        )

    # Get organization details
    statement = select(Organization).where(Organization.id == user.organization_id)
    result = await session.execute(statement)
    organization = result.scalar_one_or_none()

    if not organization:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Organización no encontrada",
        )

    return UserResponse(
        id=str(user.user_id),
        email=user.email,
        full_name=user_obj.full_name,
        organization_id=str(user.organization_id),
        organization_name=organization.name,
        role=user.role,
    )


@router.get("/invite/{token}", response_model=InviteInfoResponse)
async def get_invite_info(
    token: str,
    session: AsyncSession = Depends(get_session),
):
    """
    Get information about an invitation (public endpoint).

    Use this to validate an invitation token and get details
    before showing the registration form to the user.

    Returns: Email, organization name, role, inviter name, expiration
    """
    try:
        invite_info = await invitation_service.get_invite_info(session, token)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )

    return InviteInfoResponse(**invite_info)


@router.post("/accept-invite", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def accept_invite(
    request: AcceptInviteRequest,
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_session),
):
    """
    Accept an invitation and create a user account.

    Creates the user with the provided password and adds them
    to the organization with the role specified in the invitation.

    Returns JWT tokens so the user is automatically logged in.
    """
    try:
        user, organization, role = await invitation_service.accept_invitation(
            session=session,
            token=request.token,
            full_name=request.full_name,
            password=request.password,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )

    # Generate tokens (user is now logged in)
    access_token = auth_service.create_access_token(
        user_id=user.id,
        email=user.email,
        org_id=organization.id,
        role=role,
    )
    refresh_token = auth_service.create_refresh_token(user_id=user.id)

    # Send welcome email in background
    background_tasks.add_task(
        send_welcome_email,
        email_to=user.email,
        user_name=user.full_name,
        organization_name=organization.name,
        dashboard_url=f"{settings.frontend_url}/dashboard",
    )

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
    )
