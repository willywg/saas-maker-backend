from contextlib import asynccontextmanager

from fastapi import FastAPI
from slowapi.errors import RateLimitExceeded

from app.controllers import auth, base, organizations
from app.controllers.admin import auth_router, organizations_router, users_router
from app.core.config import settings
from app.core.middleware import setup_cors
from app.core.rate_limit import limiter, rate_limit_exceeded_handler
from app.db.session import close_db, init_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield
    await close_db()


app = FastAPI(
    title=settings.app_name,
    description="Multi-tenant SaaS platform",
    version="0.1.0",
    debug=settings.debug,
    lifespan=lifespan,
)

setup_cors(app)

# Rate limiting on auth endpoints (see app/core/rate_limit.py)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)

# Include tenant routers
app.include_router(base.router)
app.include_router(auth.router, prefix="/auth", tags=["auth"])
app.include_router(organizations.router, prefix="/organizations", tags=["organizations"])

# Include admin routers
app.include_router(auth_router, prefix="/admin/auth", tags=["admin-auth"])
app.include_router(
    organizations_router, prefix="/admin/organizations", tags=["admin-organizations"]
)
app.include_router(users_router, prefix="/admin/users", tags=["admin-users"])
