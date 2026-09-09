"""Rate limiting for authentication endpoints (slowapi, in-memory storage).

The limiter keys by client IP. Behind kamal-proxy the real IP arrives in
X-Forwarded-For, which uvicorn honors because gunicorn runs with
``--forwarded-allow-ips=*`` (see Dockerfile).

Storage is per process: with several gunicorn workers each one keeps its own
counters, so the effective limit is roughly ``limit * workers``. Good enough as
brute-force protection for a template; switch to Redis storage if you need
exact global limits.
"""

from fastapi import Request
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from app.core.config import settings

limiter = Limiter(
    key_func=get_remote_address,
    enabled=settings.rate_limit_enabled,
    headers_enabled=False,
)


def auth_limit(*_args: object) -> str:
    """Limit string for auth endpoints, read at request time so tests can tune it."""
    return settings.rate_limit_auth


async def rate_limit_exceeded_handler(request: Request, exc: Exception) -> JSONResponse:
    """Return the same ``{"detail": ...}`` shape the frontend already handles."""
    assert isinstance(exc, RateLimitExceeded)
    return JSONResponse(
        status_code=429,
        content={"detail": "Demasiados intentos. Intenta de nuevo en unos minutos."},
        headers={"Retry-After": "60"},
    )
