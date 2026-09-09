from httpx import AsyncClient

from app.core.config import settings


async def test_login_is_rate_limited(client: AsyncClient, monkeypatch):
    monkeypatch.setattr(settings, "rate_limit_auth", "3/minute")
    for _ in range(3):
        response = await client.post(
            "/auth/login", data={"username": "nobody@example.com", "password": "wrong"}
        )
        assert response.status_code == 401
    response = await client.post(
        "/auth/login", data={"username": "nobody@example.com", "password": "wrong"}
    )
    assert response.status_code == 429
    assert "detail" in response.json()
    assert response.headers.get("retry-after") == "60"


async def test_forgot_password_is_rate_limited(client: AsyncClient, monkeypatch):
    monkeypatch.setattr(settings, "rate_limit_auth", "2/minute")
    for _ in range(2):
        assert (
            await client.post("/auth/forgot-password", json={"email": "a@example.com"})
        ).status_code == 200
    assert (
        await client.post("/auth/forgot-password", json={"email": "a@example.com"})
    ).status_code == 429


async def test_admin_login_is_rate_limited(client: AsyncClient, monkeypatch):
    monkeypatch.setattr(settings, "rate_limit_auth", "2/minute")
    for _ in range(2):
        await client.post("/admin/auth/login", data={"username": "a@x.co", "password": "x"})
    response = await client.post("/admin/auth/login", data={"username": "a@x.co", "password": "x"})
    assert response.status_code == 429
