"""Shared pytest fixtures.

Strategy:
- Tests run against a dedicated Postgres database (default ``saas_template_test``).
  The name MUST contain "test" as a safety guard.
- The schema is built by running the real Alembic migrations once per session,
  so the migration chain itself is verified on every test run.
- Tables are truncated between tests.
- Outgoing email is stubbed; the password-reset email is captured so tests can
  read the raw token.
"""

import os
import subprocess
import sys
from collections.abc import AsyncGenerator

# Environment must be set BEFORE importing the app (settings load at import time).
os.environ.setdefault("POSTGRES_DB", "saas_template_test")
os.environ.setdefault("JWT_SECRET_KEY", "test-only-secret-key-0123456789abcdef0123456789")
os.environ.setdefault("DEBUG", "false")

import asyncpg  # noqa: E402
import pytest  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402
from sqlalchemy import text  # noqa: E402

from app.core.config import settings  # noqa: E402
from app.db.session import async_engine  # noqa: E402
from app.main import app  # noqa: E402

if "test" not in settings.postgres_db:
    raise RuntimeError(
        f"Refusing to run tests against '{settings.postgres_db}': "
        "the database name must contain 'test'."
    )


async def _ensure_database_exists() -> None:
    conn = await asyncpg.connect(
        host=settings.postgres_host,
        port=settings.postgres_port,
        user=settings.postgres_user,
        password=settings.postgres_password or None,
        database="postgres",
    )
    try:
        exists = await conn.fetchval(
            "SELECT 1 FROM pg_database WHERE datname = $1", settings.postgres_db
        )
        if not exists:
            await conn.execute(f'CREATE DATABASE "{settings.postgres_db}"')
    finally:
        await conn.close()


@pytest.fixture(scope="session", autouse=True)
async def database_schema() -> AsyncGenerator[None]:
    """Create the test DB if needed, reset schema and run migrations once."""
    await _ensure_database_exists()
    async with async_engine.begin() as conn:
        await conn.execute(text("DROP SCHEMA public CASCADE"))
        await conn.execute(text("CREATE SCHEMA public"))
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        env=os.environ.copy(),
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"alembic upgrade head failed:\n{result.stdout}\n{result.stderr}"
    yield
    await async_engine.dispose()


@pytest.fixture(autouse=True)
async def clean_tables(database_schema: None) -> AsyncGenerator[None]:
    """Truncate every application table between tests."""
    yield
    async with async_engine.begin() as conn:
        rows = await conn.execute(
            text(
                "SELECT tablename FROM pg_tables "
                "WHERE schemaname = 'public' AND tablename <> 'alembic_version'"
            )
        )
        tables = [r[0] for r in rows]
        if tables:
            joined = ", ".join(f'"{t}"' for t in tables)
            await conn.execute(text(f"TRUNCATE {joined} RESTART IDENTITY CASCADE"))


@pytest.fixture(autouse=True)
def stub_email(monkeypatch: pytest.MonkeyPatch) -> None:
    """Never hit SMTP from tests."""

    async def _noop(self, *args, **kwargs):  # noqa: ANN001
        return None

    from fastapi_mail import FastMail

    monkeypatch.setattr(FastMail, "send_message", _noop)


@pytest.fixture
def captured_reset_emails(monkeypatch: pytest.MonkeyPatch) -> list[dict]:
    """Capture password-reset emails (so tests can extract the raw token)."""
    captured: list[dict] = []

    async def _capture(**kwargs):
        captured.append(kwargs)

    import app.controllers.auth as auth_controller

    monkeypatch.setattr(auth_controller, "send_password_reset_email", _capture)
    return captured


@pytest.fixture
async def client() -> AsyncGenerator[AsyncClient]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


# --- Helpers -----------------------------------------------------------------

OWNER = {
    "email": "owner@example.com",
    "password": "SuperSecret123",
    "full_name": "Olivia Owner",
    "organization_name": "Acme Corp",
}


async def register(client: AsyncClient, **overrides) -> dict:
    payload = {**OWNER, **overrides}
    response = await client.post("/auth/register", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def auth_headers(tokens: dict) -> dict[str, str]:
    return {"Authorization": f"Bearer {tokens['access_token']}"}


@pytest.fixture
async def owner_tokens(client: AsyncClient) -> dict:
    return await register(client)
