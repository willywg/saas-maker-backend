"""Admin controllers package."""

from app.controllers.admin.auth import router as auth_router
from app.controllers.admin.organizations import router as organizations_router
from app.controllers.admin.users import router as users_router

__all__ = ["auth_router", "organizations_router", "users_router"]
