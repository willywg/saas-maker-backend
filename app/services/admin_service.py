"""Admin service for platform administration."""

import math
import uuid
from datetime import timedelta

from sqlmodel import func, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import settings
from app.core.time import utcnow
from app.models.admin import AdminUser
from app.models.tenant import Organization, OrganizationMember, User
from app.schemas.admin import (
    MembershipInfo,
    OrganizationDetailAdmin,
    OrganizationListItem,
    OrganizationMemberInfo,
    OrganizationUpdateAdmin,
    PaginatedResponse,
    UserDetailAdmin,
    UserListItem,
    UserOrganizationInfo,
    UserUpdateAdmin,
)
from app.services.auth_service import (
    create_token,
    hash_password,
    verify_password,
)

# --- Admin Authentication ---


def create_admin_access_token(admin_id: uuid.UUID, email: str, role: str) -> str:
    """Create an access token for an admin."""
    data = {
        "sub": str(admin_id),
        "email": email,
        "role": role,
    }
    expires_delta = timedelta(minutes=settings.access_token_expire_minutes)
    return create_token(data, expires_delta, "admin_access")


def create_admin_refresh_token(admin_id: uuid.UUID) -> str:
    """Create a refresh token for an admin."""
    data = {"sub": str(admin_id), "is_admin": True}
    expires_delta = timedelta(days=settings.refresh_token_expire_days)
    return create_token(data, expires_delta, "admin_refresh")


async def authenticate_admin(session: AsyncSession, email: str, password: str) -> AdminUser | None:
    """
    Authenticate an admin user.

    Returns AdminUser if authentication succeeds, None otherwise.
    """
    email = email.lower().strip()

    statement = select(AdminUser).where(AdminUser.email == email)
    result = await session.execute(statement)
    admin = result.scalar_one_or_none()

    if not admin or not admin.is_active:
        return None

    if not verify_password(password, admin.password_hash):
        return None

    # Update last login
    admin.last_login_at = utcnow()
    session.add(admin)
    await session.commit()
    await session.refresh(admin)

    return admin


async def get_admin_by_id(session: AsyncSession, admin_id: uuid.UUID) -> AdminUser | None:
    """Get an admin user by ID."""
    statement = select(AdminUser).where(AdminUser.id == admin_id)
    result = await session.execute(statement)
    return result.scalar_one_or_none()


async def create_admin(
    session: AsyncSession,
    email: str,
    password: str,
    full_name: str,
    role: str = "super_admin",
) -> AdminUser:
    """Create a new admin user."""
    email = email.lower().strip()

    # Check if admin exists
    statement = select(AdminUser).where(AdminUser.email == email)
    result = await session.execute(statement)
    existing = result.scalar_one_or_none()
    if existing:
        raise ValueError("Este email de admin ya está registrado")

    admin = AdminUser(
        email=email,
        password_hash=hash_password(password),
        full_name=full_name,
        role=role,
    )
    session.add(admin)
    await session.commit()
    await session.refresh(admin)

    return admin


# --- Organizations ---


async def list_organizations(
    session: AsyncSession,
    page: int = 1,
    page_size: int = 20,
    search: str | None = None,
    is_active: bool | None = None,
    sort_by: str = "created_at",
    sort_order: str = "desc",
) -> PaginatedResponse[OrganizationListItem]:
    """List all organizations with pagination and filters."""
    # Base query
    query = select(Organization)

    # Apply filters
    if search:
        search_term = f"%{search}%"
        query = query.where(
            (Organization.name.ilike(search_term)) | (Organization.slug.ilike(search_term))
        )

    if is_active is not None:
        query = query.where(Organization.is_active == is_active)

    # Get total count
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await session.execute(count_query)
    total = total_result.scalar_one()

    # Apply sorting
    sort_column = getattr(Organization, sort_by, Organization.created_at)
    if sort_order == "desc":
        query = query.order_by(sort_column.desc())
    else:
        query = query.order_by(sort_column.asc())

    # Apply pagination
    offset = (page - 1) * page_size
    query = query.offset(offset).limit(page_size)

    result = await session.execute(query)
    organizations = result.scalars().all()

    # Get member counts for each organization
    items = []
    for org in organizations:
        member_count_query = select(func.count()).where(
            OrganizationMember.organization_id == org.id
        )
        member_count_result = await session.execute(member_count_query)
        member_count = member_count_result.scalar_one()

        items.append(
            OrganizationListItem(
                id=org.id,
                name=org.name,
                slug=org.slug,
                is_active=org.is_active,
                created_at=org.created_at,
                member_count=member_count,
            )
        )

    total_pages = math.ceil(total / page_size) if total > 0 else 1

    return PaginatedResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )


async def get_organization(
    session: AsyncSession, org_id: uuid.UUID
) -> OrganizationDetailAdmin | None:
    """Get organization detail with members."""
    statement = select(Organization).where(Organization.id == org_id)
    result = await session.execute(statement)
    org = result.scalar_one_or_none()

    if not org:
        return None

    # Get members
    members_query = (
        select(User, OrganizationMember)
        .join(OrganizationMember, User.id == OrganizationMember.user_id)
        .where(OrganizationMember.organization_id == org_id)
    )
    members_result = await session.execute(members_query)
    members_data = members_result.all()

    members = [
        OrganizationMemberInfo(
            id=user.id,
            email=user.email,
            full_name=user.full_name,
            role=membership.role,
            joined_at=membership.created_at,
        )
        for user, membership in members_data
    ]

    return OrganizationDetailAdmin(
        id=org.id,
        name=org.name,
        slug=org.slug,
        is_active=org.is_active,
        created_at=org.created_at,
        updated_at=org.updated_at,
        members=members,
    )


async def update_organization(
    session: AsyncSession, org_id: uuid.UUID, data: OrganizationUpdateAdmin
) -> Organization | None:
    """Update an organization."""
    statement = select(Organization).where(Organization.id == org_id)
    result = await session.execute(statement)
    org = result.scalar_one_or_none()

    if not org:
        return None

    # Update fields
    if data.name is not None:
        org.name = data.name
    if data.slug is not None:
        org.slug = data.slug
    if data.is_active is not None:
        org.is_active = data.is_active

    org.updated_at = utcnow()
    session.add(org)
    await session.commit()
    await session.refresh(org)

    return org


async def deactivate_organization(session: AsyncSession, org_id: uuid.UUID) -> bool:
    """Soft delete an organization by setting is_active=False."""
    statement = select(Organization).where(Organization.id == org_id)
    result = await session.execute(statement)
    org = result.scalar_one_or_none()

    if not org:
        return False

    org.is_active = False
    org.updated_at = utcnow()
    session.add(org)
    await session.commit()

    return True


async def toggle_organization_status(
    session: AsyncSession, org_id: uuid.UUID, is_active: bool
) -> Organization | None:
    """Toggle organization active status."""
    statement = select(Organization).where(Organization.id == org_id)
    result = await session.execute(statement)
    org = result.scalar_one_or_none()

    if not org:
        return None

    org.is_active = is_active
    org.updated_at = utcnow()
    session.add(org)
    await session.commit()
    await session.refresh(org)

    return org


async def list_organization_users(
    session: AsyncSession,
    org_id: uuid.UUID,
    page: int = 1,
    page_size: int = 10,
) -> PaginatedResponse[UserListItem]:
    """List users in an organization with pagination."""
    # Base query - users in this organization
    query = (
        select(User, OrganizationMember.role)
        .join(OrganizationMember, User.id == OrganizationMember.user_id)
        .where(OrganizationMember.organization_id == org_id)
    )

    # Get total count
    count_query = (
        select(func.count())
        .select_from(User)
        .join(OrganizationMember, User.id == OrganizationMember.user_id)
        .where(OrganizationMember.organization_id == org_id)
    )
    total_result = await session.execute(count_query)
    total = total_result.scalar_one()

    # Apply pagination
    offset = (page - 1) * page_size
    query = query.order_by(User.created_at.desc()).offset(offset).limit(page_size)

    result = await session.execute(query)
    users_data = result.all()

    # Get organization info
    org_query = select(Organization).where(Organization.id == org_id)
    org_result = await session.execute(org_query)
    org = org_result.scalar_one_or_none()

    items = []
    for user, role in users_data:
        organization = None
        if org:
            organization = UserOrganizationInfo(
                id=org.id,
                name=org.name,
                slug=org.slug,
                role=role,
            )

        items.append(
            UserListItem(
                id=user.id,
                email=user.email,
                full_name=user.full_name,
                is_active=user.is_active,
                created_at=user.created_at,
                last_login_at=user.last_login_at,
                organization=organization,
            )
        )

    total_pages = math.ceil(total / page_size) if total > 0 else 1

    return PaginatedResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )


# --- Users ---


async def list_users(
    session: AsyncSession,
    page: int = 1,
    page_size: int = 20,
    search: str | None = None,
    is_active: bool | None = None,
    organization_id: uuid.UUID | None = None,
    sort_by: str = "created_at",
    sort_order: str = "desc",
) -> PaginatedResponse[UserListItem]:
    """List all users with pagination and filters."""
    # Base query
    query = select(User)

    # Apply filters
    if search:
        search_term = f"%{search}%"
        query = query.where((User.email.ilike(search_term)) | (User.full_name.ilike(search_term)))

    if is_active is not None:
        query = query.where(User.is_active == is_active)

    if organization_id:
        query = query.join(OrganizationMember, User.id == OrganizationMember.user_id).where(
            OrganizationMember.organization_id == organization_id
        )

    # Get total count
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await session.execute(count_query)
    total = total_result.scalar_one()

    # Apply sorting
    sort_column = getattr(User, sort_by, User.created_at)
    if sort_order == "desc":
        query = query.order_by(sort_column.desc())
    else:
        query = query.order_by(sort_column.asc())

    # Apply pagination
    offset = (page - 1) * page_size
    query = query.offset(offset).limit(page_size)

    result = await session.execute(query)
    users = result.scalars().all()

    # Get primary organization for each user
    items = []
    for user in users:
        org_query = (
            select(Organization, OrganizationMember.role)
            .join(OrganizationMember, Organization.id == OrganizationMember.organization_id)
            .where(OrganizationMember.user_id == user.id)
            .order_by(OrganizationMember.created_at.asc())
            .limit(1)
        )
        org_result = await session.execute(org_query)
        org_data = org_result.first()

        organization = None
        if org_data:
            org, role = org_data
            organization = UserOrganizationInfo(
                id=org.id,
                name=org.name,
                slug=org.slug,
                role=role,
            )

        items.append(
            UserListItem(
                id=user.id,
                email=user.email,
                full_name=user.full_name,
                is_active=user.is_active,
                created_at=user.created_at,
                last_login_at=user.last_login_at,
                organization=organization,
            )
        )

    total_pages = math.ceil(total / page_size) if total > 0 else 1

    return PaginatedResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )


async def get_user(session: AsyncSession, user_id: uuid.UUID) -> UserDetailAdmin | None:
    """Get user detail with memberships."""
    statement = select(User).where(User.id == user_id)
    result = await session.execute(statement)
    user = result.scalar_one_or_none()

    if not user:
        return None

    # Get memberships
    memberships_query = (
        select(Organization, OrganizationMember)
        .join(OrganizationMember, Organization.id == OrganizationMember.organization_id)
        .where(OrganizationMember.user_id == user_id)
    )
    memberships_result = await session.execute(memberships_query)
    memberships_data = memberships_result.all()

    memberships = [
        MembershipInfo(
            organization_id=org.id,
            organization_name=org.name,
            role=membership.role,
            joined_at=membership.created_at,
        )
        for org, membership in memberships_data
    ]

    return UserDetailAdmin(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        is_active=user.is_active,
        email_verified=user.email_verified,
        created_at=user.created_at,
        last_login_at=user.last_login_at,
        memberships=memberships,
    )


async def update_user(
    session: AsyncSession, user_id: uuid.UUID, data: UserUpdateAdmin
) -> User | None:
    """Update a user."""
    statement = select(User).where(User.id == user_id)
    result = await session.execute(statement)
    user = result.scalar_one_or_none()

    if not user:
        return None

    # Update fields
    if data.full_name is not None:
        user.full_name = data.full_name
    if data.is_active is not None:
        user.is_active = data.is_active

    session.add(user)
    await session.commit()
    await session.refresh(user)

    return user


async def deactivate_user(session: AsyncSession, user_id: uuid.UUID) -> bool:
    """Soft delete a user by setting is_active=False."""
    statement = select(User).where(User.id == user_id)
    result = await session.execute(statement)
    user = result.scalar_one_or_none()

    if not user:
        return False

    user.is_active = False
    session.add(user)
    await session.commit()

    return True


async def toggle_user_status(
    session: AsyncSession, user_id: uuid.UUID, is_active: bool
) -> User | None:
    """Toggle user active status."""
    statement = select(User).where(User.id == user_id)
    result = await session.execute(statement)
    user = result.scalar_one_or_none()

    if not user:
        return None

    user.is_active = is_active
    session.add(user)
    await session.commit()
    await session.refresh(user)

    return user


# --- Dashboard Stats ---


async def get_dashboard_stats(session: AsyncSession) -> dict:
    """Get dashboard statistics."""
    # Total organizations
    org_count_result = await session.execute(select(func.count(Organization.id)))
    total_orgs = org_count_result.scalar_one()

    # Active organizations
    active_org_result = await session.execute(
        select(func.count(Organization.id)).where(Organization.is_active == True)
    )
    active_orgs = active_org_result.scalar_one()

    # Total users
    user_count_result = await session.execute(select(func.count(User.id)))
    total_users = user_count_result.scalar_one()

    # Active users
    active_user_result = await session.execute(
        select(func.count(User.id)).where(User.is_active == True)
    )
    active_users = active_user_result.scalar_one()

    return {
        "total_organizations": total_orgs,
        "active_organizations": active_orgs,
        "total_users": total_users,
        "active_users": active_users,
    }
