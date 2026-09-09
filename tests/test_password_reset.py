from httpx import AsyncClient

from tests.conftest import OWNER


def _token_from(captured: list[dict]) -> str:
    assert len(captured) == 1
    return captured[0]["reset_url"].rsplit("/", 1)[-1]


async def test_forgot_password_does_not_leak_existence(
    client: AsyncClient, captured_reset_emails: list[dict]
):
    response = await client.post("/auth/forgot-password", json={"email": "nobody@example.com"})
    assert response.status_code == 200
    assert captured_reset_emails == []


async def test_full_reset_flow(
    client: AsyncClient, owner_tokens: dict, captured_reset_emails: list[dict]
):
    response = await client.post("/auth/forgot-password", json={"email": OWNER["email"]})
    assert response.status_code == 200
    token = _token_from(captured_reset_emails)

    # Token validation returns a masked email
    info = await client.get(f"/auth/reset-password/{token}")
    assert info.status_code == 200
    assert "***" in info.json()["email"]

    # Reset password
    reset = await client.post(
        "/auth/reset-password", json={"token": token, "new_password": "BrandNewPass789"}
    )
    assert reset.status_code == 200

    # Old password fails, new one works
    old = await client.post(
        "/auth/login", data={"username": OWNER["email"], "password": OWNER["password"]}
    )
    assert old.status_code == 401
    new = await client.post(
        "/auth/login", data={"username": OWNER["email"], "password": "BrandNewPass789"}
    )
    assert new.status_code == 200

    # Token is single-use
    again = await client.post(
        "/auth/reset-password", json={"token": token, "new_password": "YetAnotherPass000"}
    )
    assert again.status_code == 400


async def test_reset_with_invalid_token(client: AsyncClient):
    assert (await client.get("/auth/reset-password/garbage")).status_code == 400
    response = await client.post(
        "/auth/reset-password", json={"token": "garbage", "new_password": "BrandNewPass789"}
    )
    assert response.status_code == 400
