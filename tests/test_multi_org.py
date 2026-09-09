"""A user can belong to several organizations and switch the session between them."""

from httpx import AsyncClient

from tests.conftest import OWNER, auth_headers, register


async def _join_second_org(client: AsyncClient) -> tuple[dict, dict]:
    """Acme owner gets invited into Globex. Returns (acme_tokens, globex_owner_tokens)."""
    acme = await register(client)
    globex = await register(
        client, email="globex@example.com", organization_name="Globex", full_name="Gina"
    )
    invite = await client.post(
        "/organizations/members/invite",
        json={"email": OWNER["email"], "role": "admin"},
        headers=auth_headers(globex),
    )
    assert invite.status_code == 201
    accept = await client.post(
        "/auth/accept-invite",
        json={
            "token": invite.json()["token"],
            "full_name": OWNER["full_name"],
            "password": OWNER["password"],
        },
    )
    assert accept.status_code == 201, accept.text
    return acme, globex


async def test_list_organizations_marks_current(client: AsyncClient):
    acme, _ = await _join_second_org(client)
    response = await client.get("/auth/organizations", headers=auth_headers(acme))
    assert response.status_code == 200
    orgs = {o["name"]: o for o in response.json()}
    assert set(orgs) == {"Acme Corp", "Globex"}
    assert orgs["Acme Corp"]["role"] == "owner" and orgs["Acme Corp"]["is_current"] is True
    assert orgs["Globex"]["role"] == "admin" and orgs["Globex"]["is_current"] is False


async def test_switch_organization_and_refresh_keeps_it(client: AsyncClient):
    acme, _ = await _join_second_org(client)
    orgs = (await client.get("/auth/organizations", headers=auth_headers(acme))).json()
    globex_id = next(o["id"] for o in orgs if o["name"] == "Globex")

    switched = await client.post(
        "/auth/switch-organization",
        json={"organization_id": globex_id, "refresh_token": acme["refresh_token"]},
        headers=auth_headers(acme),
    )
    assert switched.status_code == 200
    globex_tokens = switched.json()

    me = await client.get("/auth/me", headers=auth_headers(globex_tokens))
    assert me.json()["organization_name"] == "Globex"
    assert me.json()["role"] == "admin"

    # The previous refresh token was revoked on switch
    old = await client.post("/auth/refresh", json={"refresh_token": acme["refresh_token"]})
    assert old.status_code == 401

    # Refreshing stays on Globex (does not fall back to the first org)
    refreshed = await client.post(
        "/auth/refresh", json={"refresh_token": globex_tokens["refresh_token"]}
    )
    assert refreshed.status_code == 200
    me = await client.get("/auth/me", headers=auth_headers(refreshed.json()))
    assert me.json()["organization_name"] == "Globex"


async def test_cannot_switch_to_foreign_organization(client: AsyncClient):
    acme = await register(client)
    other = await register(client, email="x@example.com", organization_name="Other")
    other_org_id = (await client.get("/auth/me", headers=auth_headers(other))).json()[
        "organization_id"
    ]
    response = await client.post(
        "/auth/switch-organization",
        json={"organization_id": other_org_id},
        headers=auth_headers(acme),
    )
    assert response.status_code == 403
