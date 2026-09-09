from httpx import AsyncClient

from tests.conftest import auth_headers, register

INVITEE = {"email": "member@example.com", "role": "member"}


async def _invite(client: AsyncClient, tokens: dict, **overrides) -> dict:
    response = await client.post(
        "/organizations/members/invite", json={**INVITEE, **overrides}, headers=auth_headers(tokens)
    )
    assert response.status_code == 201, response.text
    return response.json()


async def _accept(client: AsyncClient, token: str, **overrides) -> dict:
    payload = {"token": token, "full_name": "Mia Member", "password": "MemberPass123", **overrides}
    response = await client.post("/auth/accept-invite", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


async def test_get_and_update_organization(client: AsyncClient, owner_tokens: dict):
    me = await client.get("/organizations/me", headers=auth_headers(owner_tokens))
    assert me.status_code == 200
    assert me.json()["name"] == "Acme Corp"

    updated = await client.put(
        "/organizations/me", json={"name": "Acme Inc"}, headers=auth_headers(owner_tokens)
    )
    assert updated.status_code == 200
    assert updated.json()["name"] == "Acme Inc"


async def test_invite_and_accept_flow(client: AsyncClient, owner_tokens: dict):
    invite = await _invite(client, owner_tokens)
    assert invite["email"] == INVITEE["email"]
    assert invite["token"] in invite["invite_url"]

    # Public invite info
    info = await client.get(f"/auth/invite/{invite['token']}")
    assert info.status_code == 200
    assert info.json()["organization_name"] == "Acme Corp"
    assert info.json()["role"] == "member"

    # Accept → logged-in member of the org
    member_tokens = await _accept(client, invite["token"])
    me = await client.get("/auth/me", headers=auth_headers(member_tokens))
    assert me.status_code == 200
    assert me.json()["role"] == "member"
    assert me.json()["organization_name"] == "Acme Corp"

    # Token is single-use
    again = await client.post(
        "/auth/accept-invite",
        json={"token": invite["token"], "full_name": "X", "password": "MemberPass123"},
    )
    assert again.status_code == 400

    # Owner sees both members
    members = await client.get("/organizations/members", headers=auth_headers(owner_tokens))
    assert members.status_code == 200
    emails = {m["email"] for m in members.json()}
    assert emails == {"owner@example.com", "member@example.com"}


async def test_member_cannot_invite_or_list_members(client: AsyncClient, owner_tokens: dict):
    invite = await _invite(client, owner_tokens)
    member_tokens = await _accept(client, invite["token"])

    forbidden = await client.post(
        "/organizations/members/invite",
        json={"email": "x@example.com", "role": "member"},
        headers=auth_headers(member_tokens),
    )
    assert forbidden.status_code == 403
    assert (
        await client.get("/organizations/members", headers=auth_headers(member_tokens))
    ).status_code == 403


async def test_invite_cannot_grant_owner_role(client: AsyncClient, owner_tokens: dict):
    response = await client.post(
        "/organizations/members/invite",
        json={"email": "x@example.com", "role": "owner"},
        headers=auth_headers(owner_tokens),
    )
    assert response.status_code == 422


async def test_owner_can_change_role_and_remove_member(client: AsyncClient, owner_tokens: dict):
    invite = await _invite(client, owner_tokens)
    member_tokens = await _accept(client, invite["token"])
    member_id = (await client.get("/auth/me", headers=auth_headers(member_tokens))).json()["id"]

    promoted = await client.put(
        f"/organizations/members/{member_id}/role",
        json={"role": "admin"},
        headers=auth_headers(owner_tokens),
    )
    assert promoted.status_code == 200
    assert promoted.json()["role"] == "admin"

    removed = await client.delete(
        f"/organizations/members/{member_id}", headers=auth_headers(owner_tokens)
    )
    assert removed.status_code in (200, 204)

    members = await client.get("/organizations/members", headers=auth_headers(owner_tokens))
    assert {m["email"] for m in members.json()} == {"owner@example.com"}


async def test_tenant_isolation(client: AsyncClient):
    a = await register(client)
    b = await register(
        client, email="other@example.com", organization_name="Globex", full_name="Bob"
    )
    members_a = await client.get("/organizations/members", headers=auth_headers(a))
    members_b = await client.get("/organizations/members", headers=auth_headers(b))
    assert {m["email"] for m in members_a.json()} == {"owner@example.com"}
    assert {m["email"] for m in members_b.json()} == {"other@example.com"}
