"""FastAPI dependencies for authentication and authorization."""

import uuid
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer

from app.schemas.admin import AdminAuthUser
from app.schemas.auth import AuthUser
from app.services.auth_service import decode_token

# OAuth2 scheme for Swagger UI - Tenant users
# This tells FastAPI to show the "Authorize" button in docs
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")

# OAuth2 scheme for Admin users - separate auth flow
admin_oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/admin/auth/login")


async def get_current_user(token: Annotated[str, Depends(oauth2_scheme)]) -> AuthUser:
    """
    Dependency to get the current authenticated user from JWT token.

    Raises:
        HTTPException: 401 if token is invalid or missing required fields
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="No se pudieron validar las credenciales",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        payload = decode_token(token)

        # Verify token type
        if payload.get("type") != "access":
            raise credentials_exception

        # Extract user data
        user_id = payload.get("sub")
        email = payload.get("email")
        org_id = payload.get("org_id")
        role = payload.get("role")

        if not user_id or not email or not org_id or not role:
            raise credentials_exception

        return AuthUser(
            user_id=uuid.UUID(user_id),
            email=email,
            organization_id=uuid.UUID(org_id),
            role=role,
        )

    except (ValueError, KeyError):
        raise credentials_exception


def require_role(min_role: str):
    """
    Factory to create a dependency that requires a minimum role.

    Usage:
        @router.delete("/{id}", dependencies=[Depends(require_role("admin"))])
        async def delete_resource(...):
            ...

    Args:
        min_role: Minimum required role ("member", "admin", or "owner")

    Returns:
        Dependency function that validates role
    """

    async def role_checker(user: AuthUser = Depends(get_current_user)) -> AuthUser:
        if not user.has_role(min_role):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Permisos insuficientes. Se requiere rol: {min_role} o superior",
            )
        return user

    return role_checker


# Type alias for convenience
CurrentUser = Annotated[AuthUser, Depends(get_current_user)]


# --- Admin Authentication ---


async def get_current_admin(
    token: Annotated[str, Depends(admin_oauth2_scheme)],
) -> AdminAuthUser:
    """
    Dependency to get the current authenticated admin from JWT token.

    Admin tokens have type="admin_access" to distinguish from user tokens.

    Raises:
        HTTPException: 401 if token is invalid or not an admin token
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="No se pudieron validar las credenciales de admin",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        payload = decode_token(token)

        # Verify token type is admin
        if payload.get("type") != "admin_access":
            raise credentials_exception

        admin_id = payload.get("sub")
        email = payload.get("email")
        role = payload.get("role")

        if not admin_id or not email or not role:
            raise credentials_exception

        return AdminAuthUser(
            admin_id=uuid.UUID(admin_id),
            email=email,
            role=role,
        )

    except (ValueError, KeyError):
        raise credentials_exception


def require_admin(min_role: str = "super_admin"):
    """
    Factory to create a dependency that requires admin authentication.

    For now only super_admin exists, but prepared for future roles.

    Usage:
        @router.get("/admin/users", dependencies=[Depends(require_admin())])
        async def list_users(...):
            ...
    """

    async def admin_checker(
        admin: AdminAuthUser = Depends(get_current_admin),
    ) -> AdminAuthUser:
        # Future: implement role hierarchy for support, viewer, etc.
        if admin.role != min_role and min_role == "super_admin":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Permisos de admin insuficientes",
            )
        return admin

    return admin_checker


# Type alias for admin
CurrentAdmin = Annotated[AdminAuthUser, Depends(get_current_admin)]
