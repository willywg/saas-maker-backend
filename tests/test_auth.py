from httpx import AsyncClient

from tests.conftest import OWNER, auth_headers, register


async def test_register_returns_tokens_and_owner_role(client: AsyncClient):
    tokens = await register(client)
    assert tokens["token_type"] == "bearer"
    assert tokens["access_token"] and tokens["refresh_token"]

    me = await client.get("/auth/me", headers=auth_headers(tokens))
    assert me.status_code == 200
    body = me.json()
    assert body["email"] == OWNER["email"]
    assert body["role"] == "owner"
    assert body["organization_name"] == OWNER["organization_name"]


async def test_register_rejects_duplicate_email(client: AsyncClient):
    await register(client)
    response = await client.post("/auth/register", json={**OWNER, "organization_name": "Other Org"})
    assert response.status_code == 400
    assert "registrado" in response.json()["detail"]


async def test_register_rejects_duplicate_org_slug(client: AsyncClient):
    await register(client)
    response = await client.post("/auth/register", json={**OWNER, "email": "other@example.com"})
    assert response.status_code == 400


async def test_register_validates_password_length(client: AsyncClient):
    response = await client.post("/auth/register", json={**OWNER, "password": "short"})
    assert response.status_code == 422


async def test_login_with_form_data(client: AsyncClient, owner_tokens: dict):
    response = await client.post(
        "/auth/login", data={"username": OWNER["email"], "password": OWNER["password"]}
    )
    assert response.status_code == 200
    assert response.json()["access_token"]


async def test_login_is_case_insensitive_on_email(client: AsyncClient, owner_tokens: dict):
    response = await client.post(
        "/auth/login", data={"username": OWNER["email"].upper(), "password": OWNER["password"]}
    )
    assert response.status_code == 200


async def test_login_rejects_wrong_password(client: AsyncClient, owner_tokens: dict):
    response = await client.post(
        "/auth/login", data={"username": OWNER["email"], "password": "wrong-password"}
    )
    assert response.status_code == 401


async def test_me_requires_token(client: AsyncClient):
    assert (await client.get("/auth/me")).status_code == 401
    bad = await client.get("/auth/me", headers={"Authorization": "Bearer not-a-jwt"})
    assert bad.status_code == 401


async def test_refresh_token_rotates_tokens(client: AsyncClient, owner_tokens: dict):
    response = await client.post(
        "/auth/refresh", json={"refresh_token": owner_tokens["refresh_token"]}
    )
    assert response.status_code == 200
    new_tokens = response.json()
    assert new_tokens["access_token"]
    me = await client.get("/auth/me", headers=auth_headers(new_tokens))
    assert me.status_code == 200


async def test_refresh_rejects_access_token(client: AsyncClient, owner_tokens: dict):
    response = await client.post(
        "/auth/refresh", json={"refresh_token": owner_tokens["access_token"]}
    )
    assert response.status_code == 401


async def test_update_profile(client: AsyncClient, owner_tokens: dict):
    response = await client.put(
        "/auth/me", json={"full_name": "New Name"}, headers=auth_headers(owner_tokens)
    )
    assert response.status_code == 200
    assert response.json()["full_name"] == "New Name"


async def test_change_password_then_login_with_new_one(client: AsyncClient, owner_tokens: dict):
    response = await client.post(
        "/auth/change-password",
        json={"current_password": OWNER["password"], "new_password": "AnotherSecret456"},
        headers=auth_headers(owner_tokens),
    )
    assert response.status_code == 200

    old = await client.post(
        "/auth/login", data={"username": OWNER["email"], "password": OWNER["password"]}
    )
    assert old.status_code == 401
    new = await client.post(
        "/auth/login", data={"username": OWNER["email"], "password": "AnotherSecret456"}
    )
    assert new.status_code == 200


async def test_change_password_rejects_wrong_current(client: AsyncClient, owner_tokens: dict):
    response = await client.post(
        "/auth/change-password",
        json={"current_password": "nope-nope-nope", "new_password": "AnotherSecret456"},
        headers=auth_headers(owner_tokens),
    )
    assert response.status_code == 400
