from httpx import AsyncClient

from app.core.config import settings
from tests.conftest import OWNER, auth_headers, register


def _token_from(captured: list[dict]) -> str:
    assert captured, "no verification email captured"
    return captured[-1]["verify_url"].rsplit("/", 1)[-1]


async def test_register_sends_verification_and_me_reports_status(
    client: AsyncClient, captured_verification_emails: list[dict]
):
    tokens = await register(client)
    me = await client.get("/auth/me", headers=auth_headers(tokens))
    assert me.json()["email_verified"] is False
    assert captured_verification_emails[0]["email_to"] == OWNER["email"]

    token = _token_from(captured_verification_emails)
    verify = await client.post("/auth/verify-email", json={"token": token})
    assert verify.status_code == 200

    me = await client.get("/auth/me", headers=auth_headers(tokens))
    assert me.json()["email_verified"] is True

    # Single use
    assert (await client.post("/auth/verify-email", json={"token": token})).status_code == 400


async def test_invalid_verification_token(client: AsyncClient):
    assert (await client.post("/auth/verify-email", json={"token": "nope"})).status_code == 400


async def test_resend_verification_issues_new_token_and_invalidates_old(
    client: AsyncClient, captured_verification_emails: list[dict]
):
    tokens = await register(client)
    old_token = _token_from(captured_verification_emails)

    resend = await client.post("/auth/resend-verification", headers=auth_headers(tokens))
    assert resend.status_code == 200
    new_token = _token_from(captured_verification_emails)
    assert new_token != old_token

    assert (await client.post("/auth/verify-email", json={"token": old_token})).status_code == 400
    assert (await client.post("/auth/verify-email", json={"token": new_token})).status_code == 200

    # Already verified → informative 200, no new email
    sent_before = len(captured_verification_emails)
    resend = await client.post("/auth/resend-verification", headers=auth_headers(tokens))
    assert resend.status_code == 200
    assert len(captured_verification_emails) == sent_before


async def test_invited_users_are_verified_automatically(
    client: AsyncClient, owner_tokens: dict, captured_verification_emails: list[dict]
):
    invite = await client.post(
        "/organizations/members/invite",
        json={"email": "member@example.com", "role": "member"},
        headers=auth_headers(owner_tokens),
    )
    accept = await client.post(
        "/auth/accept-invite",
        json={"token": invite.json()["token"], "full_name": "Mia", "password": "MemberPass123"},
    )
    me = await client.get("/auth/me", headers=auth_headers(accept.json()))
    assert me.json()["email_verified"] is True


async def test_require_email_verification_blocks_login_until_verified(
    client: AsyncClient, captured_verification_emails: list[dict], monkeypatch
):
    monkeypatch.setattr(settings, "require_email_verification", True)
    await register(client)

    login = await client.post(
        "/auth/login", data={"username": OWNER["email"], "password": OWNER["password"]}
    )
    assert login.status_code == 403

    token = _token_from(captured_verification_emails)
    await client.post("/auth/verify-email", json={"token": token})

    login = await client.post(
        "/auth/login", data={"username": OWNER["email"], "password": OWNER["password"]}
    )
    assert login.status_code == 200
