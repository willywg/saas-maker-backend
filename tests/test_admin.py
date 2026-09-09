import pytest
from httpx import AsyncClient

from app.db.session import async_session_factory
from app.services.admin_service import create_admin
from tests.conftest import auth_headers, register

ADMIN = {"email": "root@example.com", "password": "AdminPass123", "full_name": "Root Admin"}


@pytest.fixture
async def admin_tokens(client: AsyncClient) -> dict:
    async with async_session_factory() as session:
        await create_admin(session, **ADMIN)
    response = await client.post(
        "/admin/auth/login", data={"username": ADMIN["email"], "password": ADMIN["password"]}
    )
    assert response.status_code == 200, response.text
    return response.json()


async def test_admin_login_rejects_bad_credentials(client: AsyncClient, admin_tokens: dict):
    response = await client.post(
        "/admin/auth/login", data={"username": ADMIN["email"], "password": "wrong"}
    )
    assert response.status_code == 401


async def test_tenant_token_cannot_access_admin_api(client: AsyncClient, owner_tokens: dict):
    response = await client.get("/admin/users", headers=auth_headers(owner_tokens))
    assert response.status_code == 401


async def test_admin_token_cannot_access_tenant_api(client: AsyncClient, admin_tokens: dict):
    response = await client.get("/auth/me", headers=auth_headers(admin_tokens))
    assert response.status_code == 401


async def test_admin_lists_organizations_and_users(client: AsyncClient, admin_tokens: dict):
    await register(client)
    await register(client, email="other@example.com", organization_name="Globex")

    me = await client.get("/admin/auth/me", headers=auth_headers(admin_tokens))
    assert me.status_code == 200
    assert me.json()["email"] == ADMIN["email"]

    orgs = await client.get("/admin/organizations", headers=auth_headers(admin_tokens))
    assert orgs.status_code == 200
    assert orgs.json()["total"] == 2

    users = await client.get("/admin/users", headers=auth_headers(admin_tokens))
    assert users.status_code == 200
    assert users.json()["total"] == 2

    stats = await client.get("/admin/users/stats", headers=auth_headers(admin_tokens))
    assert stats.status_code == 200


async def test_admin_can_deactivate_organization(client: AsyncClient, admin_tokens: dict):
    owner = await register(client)
    org_id = (await client.get("/auth/me", headers=auth_headers(owner))).json()["organization_id"]

    toggled = await client.patch(
        f"/admin/organizations/{org_id}/status",
        json={"is_active": False},
        headers=auth_headers(admin_tokens),
    )
    assert toggled.status_code == 200
    assert toggled.json()["is_active"] is False

    # Owner can no longer log in to an inactive org
    login = await client.post(
        "/auth/login", data={"username": "owner@example.com", "password": "SuperSecret123"}
    )
    assert login.status_code == 401
