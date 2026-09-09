from httpx import AsyncClient


async def test_root(client: AsyncClient):
    response = await client.get("/")
    assert response.status_code == 200
    assert "message" in response.json()


async def test_health_check_reports_database(client: AsyncClient):
    response = await client.get("/up")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["database"] == "connected"
