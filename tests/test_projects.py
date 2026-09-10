"""Projects: the reference tenant-scoped resource.

Covers the CRUD, the role split (read: member, write: admin+), and the
isolation guarantee: another organization can never see or touch a project.
"""

import uuid

from httpx import AsyncClient

from tests.conftest import auth_headers, register


async def _add_member(client: AsyncClient, admin_tokens: dict, email: str, role: str) -> dict:
    invite = await client.post(
        "/organizations/members/invite",
        json={"email": email, "role": role},
        headers=auth_headers(admin_tokens),
    )
    assert invite.status_code == 201, invite.text
    accept = await client.post(
        "/auth/accept-invite",
        json={
            "token": invite.json()["token"],
            "full_name": "Nuevo Miembro",
            "password": "MemberPass123",
        },
    )
    assert accept.status_code == 201, accept.text
    return accept.json()


async def _create(client: AsyncClient, tokens: dict, **overrides) -> dict:
    payload = {"name": "Sitio web", "description": "Rediseño", "status": "active", **overrides}
    response = await client.post("/projects", json=payload, headers=auth_headers(tokens))
    assert response.status_code == 201, response.text
    return response.json()


# --- CRUD -------------------------------------------------------------------


async def test_create_and_get_project(client: AsyncClient, owner_tokens: dict):
    created = await _create(client, owner_tokens)
    assert created["name"] == "Sitio web"
    assert created["status"] == "active"
    assert created["created_by"] is not None

    fetched = await client.get(f"/projects/{created['id']}", headers=auth_headers(owner_tokens))
    assert fetched.status_code == 200
    assert fetched.json() == created


async def test_list_is_paginated_newest_first_and_searchable(
    client: AsyncClient, owner_tokens: dict
):
    for name in ["Alpha", "Beta", "Gamma"]:
        await _create(client, owner_tokens, name=name)

    page = await client.get(
        "/projects", params={"page_size": 2}, headers=auth_headers(owner_tokens)
    )
    assert page.status_code == 200
    body = page.json()
    assert body["total"] == 3 and body["page"] == 1 and body["page_size"] == 2
    assert [p["name"] for p in body["items"]] == ["Gamma", "Beta"]

    page2 = await client.get(
        "/projects", params={"page_size": 2, "page": 2}, headers=auth_headers(owner_tokens)
    )
    assert [p["name"] for p in page2.json()["items"]] == ["Alpha"]

    search = await client.get("/projects", params={"q": "bet"}, headers=auth_headers(owner_tokens))
    assert [p["name"] for p in search.json()["items"]] == ["Beta"]

    await _create(client, owner_tokens, name="Done one", status="done")
    done = await client.get(
        "/projects", params={"status": "done"}, headers=auth_headers(owner_tokens)
    )
    assert [p["name"] for p in done.json()["items"]] == ["Done one"]


async def test_update_and_delete_project(client: AsyncClient, owner_tokens: dict):
    created = await _create(client, owner_tokens)

    updated = await client.put(
        f"/projects/{created['id']}",
        json={"status": "done", "description": None},
        headers=auth_headers(owner_tokens),
    )
    assert updated.status_code == 200
    assert updated.json()["status"] == "done"
    assert updated.json()["description"] is None
    assert updated.json()["name"] == "Sitio web"  # untouched
    assert updated.json()["updated_at"] >= created["updated_at"]

    deleted = await client.delete(f"/projects/{created['id']}", headers=auth_headers(owner_tokens))
    assert deleted.status_code == 204

    gone = await client.get(f"/projects/{created['id']}", headers=auth_headers(owner_tokens))
    assert gone.status_code == 404


async def test_validation(client: AsyncClient, owner_tokens: dict):
    headers = auth_headers(owner_tokens)
    assert (await client.post("/projects", json={"name": ""}, headers=headers)).status_code == 422
    assert (
        await client.post("/projects", json={"name": "x", "status": "weird"}, headers=headers)
    ).status_code == 422
    assert (await client.get("/projects/not-a-uuid", headers=headers)).status_code == 422
    assert (await client.get(f"/projects/{uuid.uuid4()}", headers=headers)).status_code == 404


# --- Roles ------------------------------------------------------------------


async def test_member_can_read_but_not_write(client: AsyncClient, owner_tokens: dict):
    project = await _create(client, owner_tokens)
    member = await _add_member(client, owner_tokens, "member@example.com", "member")
    headers = auth_headers(member)

    assert (await client.get("/projects", headers=headers)).json()["total"] == 1
    assert (await client.get(f"/projects/{project['id']}", headers=headers)).status_code == 200

    assert (await client.post("/projects", json={"name": "No"}, headers=headers)).status_code == 403
    assert (
        await client.put(f"/projects/{project['id']}", json={"name": "No"}, headers=headers)
    ).status_code == 403
    assert (await client.delete(f"/projects/{project['id']}", headers=headers)).status_code == 403


async def test_admin_can_write(client: AsyncClient, owner_tokens: dict):
    admin = await _add_member(client, owner_tokens, "admin@example.com", "admin")
    project = await _create(client, admin, name="Por admin")
    assert (
        await client.put(
            f"/projects/{project['id']}", json={"name": "Editado"}, headers=auth_headers(admin)
        )
    ).json()["name"] == "Editado"
    assert (
        await client.delete(f"/projects/{project['id']}", headers=auth_headers(admin))
    ).status_code == 204


async def test_requires_authentication(client: AsyncClient):
    assert (await client.get("/projects")).status_code == 401
    assert (await client.post("/projects", json={"name": "x"})).status_code == 401


# --- Isolation between organizations ----------------------------------------


async def test_other_organization_cannot_see_or_touch_projects(client: AsyncClient):
    acme = await register(client)
    globex = await register(
        client, email="globex@example.com", organization_name="Globex", full_name="Gina"
    )
    acme_project = await _create(client, acme, name="Acme only")
    await _create(client, globex, name="Globex only")

    # Listing only shows the caller's organization
    acme_list = await client.get("/projects", headers=auth_headers(acme))
    assert [p["name"] for p in acme_list.json()["items"]] == ["Acme only"]
    globex_list = await client.get("/projects", headers=auth_headers(globex))
    assert [p["name"] for p in globex_list.json()["items"]] == ["Globex only"]

    # Direct access from the other organization looks like "not found"
    other = auth_headers(globex)
    pid = acme_project["id"]
    assert (await client.get(f"/projects/{pid}", headers=other)).status_code == 404
    assert (
        await client.put(f"/projects/{pid}", json={"name": "Hacked"}, headers=other)
    ).status_code == 404
    assert (await client.delete(f"/projects/{pid}", headers=other)).status_code == 404

    # ...and the project is intact
    still = await client.get(f"/projects/{pid}", headers=auth_headers(acme))
    assert still.status_code == 200 and still.json()["name"] == "Acme only"


async def test_switching_organization_switches_projects(client: AsyncClient):
    """A multi-org user sees the projects of the organization their session is scoped to."""
    acme = await register(client)
    globex = await register(
        client, email="globex@example.com", organization_name="Globex", full_name="Gina"
    )
    await _create(client, acme, name="Acme only")
    await _create(client, globex, name="Globex only")

    # Acme's owner joins Globex as admin
    invite = await client.post(
        "/organizations/members/invite",
        json={"email": "owner@example.com", "role": "admin"},
        headers=auth_headers(globex),
    )
    assert invite.status_code == 201
    joined = await client.post(
        "/auth/accept-invite",
        json={"token": invite.json()["token"], "full_name": "Olivia", "password": "SuperSecret123"},
    )
    assert joined.status_code == 201

    orgs = (await client.get("/auth/organizations", headers=auth_headers(acme))).json()
    globex_id = next(o["id"] for o in orgs if o["name"] == "Globex")
    switched = await client.post(
        "/auth/switch-organization",
        json={"organization_id": globex_id, "refresh_token": acme["refresh_token"]},
        headers=auth_headers(acme),
    )
    assert switched.status_code == 200

    names = [
        p["name"]
        for p in (await client.get("/projects", headers=auth_headers(switched.json()))).json()[
            "items"
        ]
    ]
    assert names == ["Globex only"]
