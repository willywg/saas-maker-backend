"""Authentication service for user registration, login, and JWT token management."""

import uuid
from datetime import datetime, timedelta

from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import settings
from app.models import Organization, OrganizationMember, User

# Password hashing context
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    """Hash a password using bcrypt."""
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against a hash."""
    return pwd_context.verify(plain_password, hashed_password)


def create_token(data: dict, expires_delta: timedelta, token_type: str) -> str:
    """Create a JWT token (access or refresh)."""
    to_encode = data.copy()
    expire = datetime.utcnow() + expires_delta
    to_encode.update({"exp": expire, "type": token_type})

    encoded_jwt = jwt.encode(
        to_encode, settings.jwt_secret_key, algorithm=settings.jwt_algorithm
    )
    return encoded_jwt


def create_access_token(user_id: uuid.UUID, email: str, org_id: uuid.UUID, role: str) -> str:
    """Create an access token for a user."""
    data = {
        "sub": str(user_id),
        "email": email,
        "org_id": str(org_id),
        "role": role,
    }
    expires_delta = timedelta(minutes=settings.access_token_expire_minutes)
    return create_token(data, expires_delta, "access")


def create_refresh_token(user_id: uuid.UUID) -> str:
    """Create a refresh token for a user."""
    data = {"sub": str(user_id)}
    expires_delta = timedelta(days=settings.refresh_token_expire_days)
    return create_token(data, expires_delta, "refresh")


def decode_token(token: str) -> dict:
    """Decode and validate a JWT token."""
    try:
        payload = jwt.decode(
            token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm]
        )
        return payload
    except JWTError:
        raise ValueError("Token inválido")


async def register_user(
    session: AsyncSession, email: str, password: str, full_name: str | None, org_name: str
) -> tuple[User, Organization]:
    """
    Register a new user and create their organization.

    Returns (user, organization) tuple.
    """
    # Normalize email
    email = email.lower().strip()

    # Check if user exists
    statement = select(User).where(User.email == email)
    result = await session.execute(statement)
    existing_user = result.scalar_one_or_none()
    if existing_user:
        raise ValueError("Este email ya está registrado")

    # Create organization slug
    org_slug = org_name.lower().replace(" ", "-").replace("_", "-")

    # Check if slug already exists
    slug_check = select(Organization).where(Organization.slug == org_slug)
    slug_result = await session.execute(slug_check)
    if slug_result.scalar_one_or_none():
        raise ValueError(f"Ya existe una organización con el nombre '{org_name}'")

    organization = Organization(
        name=org_name,
        slug=org_slug,
    )
    session.add(organization)

    # Create user
    password_hash = hash_password(password)
    user = User(
        email=email,
        password_hash=password_hash,
        full_name=full_name,
    )
    session.add(user)

    # Flush to get IDs
    await session.flush()

    # Create membership (user is owner of their org)
    membership = OrganizationMember(
        organization_id=organization.id,
        user_id=user.id,
        role="owner",
    )
    session.add(membership)

    await session.commit()
    await session.refresh(user)
    await session.refresh(organization)

    return user, organization


async def authenticate_user(
    session: AsyncSession, email: str, password: str
) -> tuple[User, Organization, str] | None:
    """
    Authenticate a user and return (user, organization, role).

    Returns None if authentication fails.
    """
    email = email.lower().strip()

    # Get user
    statement = select(User).where(User.email == email)
    result = await session.execute(statement)
    user = result.scalar_one_or_none()

    if not user or not user.is_active:
        return None

    # Verify password
    if not verify_password(password, user.password_hash):
        return None

    # Get user's primary organization (first one they belong to)
    # TODO: In the future, allow user to select which org to log into
    statement = (
        select(Organization, OrganizationMember.role)
        .join(OrganizationMember, Organization.id == OrganizationMember.organization_id)
        .where(OrganizationMember.user_id == user.id)
        .where(Organization.is_active == True)
    )
    result = await session.execute(statement)
    org_data = result.first()

    if not org_data:
        return None

    organization, role = org_data

    # Update last login
    user.last_login_at = datetime.utcnow()
    session.add(user)
    await session.commit()

    return user, organization, role
