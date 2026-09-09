"""Refresh-token rotation and revocation (logout, logout-all, password change)."""

from httpx import AsyncClient

from tests.conftest import OWNER, auth_headers


async def _refresh(client: AsyncClient, token: str):
    return await client.post("/auth/refresh", json={"refresh_token": token})


async def test_refresh_rotates_and_old_token_is_revoked(client: AsyncClient, owner_tokens: dict):
    first = await _refresh(client, owner_tokens["refresh_token"])
    assert first.status_code == 200
    new_refresh = first.json()["refresh_token"]
    assert new_refresh != owner_tokens["refresh_token"]

    # Reusing the old refresh token fails (rotation)
    assert (await _refresh(client, owner_tokens["refresh_token"])).status_code == 401
    # The new one works
    assert (await _refresh(client, new_refresh)).status_code == 200


async def test_logout_revokes_refresh_token(client: AsyncClient, owner_tokens: dict):
    response = await client.post(
        "/auth/logout", json={"refresh_token": owner_tokens["refresh_token"]}
    )
    assert response.status_code == 200
    assert (await _refresh(client, owner_tokens["refresh_token"])).status_code == 401
    # Access token keeps working until it expires (stateless)
    assert (await client.get("/auth/me", headers=auth_headers(owner_tokens))).status_code == 200


async def test_logout_all_revokes_every_session(client: AsyncClient, owner_tokens: dict):
    second = await client.post(
        "/auth/login", data={"username": OWNER["email"], "password": OWNER["password"]}
    )
    second_tokens = second.json()

    response = await client.post("/auth/logout-all", headers=auth_headers(owner_tokens))
    assert response.status_code == 200
    assert "2" in response.json()["message"]

    assert (await _refresh(client, owner_tokens["refresh_token"])).status_code == 401
    assert (await _refresh(client, second_tokens["refresh_token"])).status_code == 401


async def test_change_password_revokes_other_sessions_but_keeps_own(
    client: AsyncClient, owner_tokens: dict
):
    other = (
        await client.post(
            "/auth/login", data={"username": OWNER["email"], "password": OWNER["password"]}
        )
    ).json()

    response = await client.post(
        "/auth/change-password",
        json={
            "current_password": OWNER["password"],
            "new_password": "AnotherSecret456",
            "refresh_token": owner_tokens["refresh_token"],
        },
        headers=auth_headers(owner_tokens),
    )
    assert response.status_code == 200

    assert (await _refresh(client, other["refresh_token"])).status_code == 401
    assert (await _refresh(client, owner_tokens["refresh_token"])).status_code == 200


async def test_password_reset_revokes_all_sessions(
    client: AsyncClient, owner_tokens: dict, captured_reset_emails: list[dict]
):
    await client.post("/auth/forgot-password", json={"email": OWNER["email"]})
    token = captured_reset_emails[0]["reset_url"].rsplit("/", 1)[-1]
    reset = await client.post(
        "/auth/reset-password", json={"token": token, "new_password": "BrandNewPass789"}
    )
    assert reset.status_code == 200
    assert (await _refresh(client, owner_tokens["refresh_token"])).status_code == 401


async def test_tampered_refresh_token_is_rejected(client: AsyncClient, owner_tokens: dict):
    assert (await _refresh(client, owner_tokens["refresh_token"] + "x")).status_code == 401
