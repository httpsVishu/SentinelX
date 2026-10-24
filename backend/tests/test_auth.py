"""Authentication: login, tokens, deactivated accounts and audit logging."""
from datetime import timedelta

from sqlalchemy import select

from app.core.security import (
    TokenType,
    _create_token,
    create_access_token,
    create_refresh_token,
    verify_password,
)
from app.models.audit_log import AuditLog
from app.models.enums import AuditAction
from tests.factories import DEFAULT_PASSWORD, bearer, make_admin

LOGIN = "/api/v1/auth/login"
REFRESH = "/api/v1/auth/refresh"
ME = "/api/v1/users/me"


def login(client, email: str, password: str):
    return client.post(LOGIN, json={"email": email, "password": password})


def test_login_returns_tokens_that_open_the_api(client, admin):
    response = login(client, admin.email, DEFAULT_PASSWORD)

    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer"

    me = client.get(ME, headers={"Authorization": f"Bearer {body['access_token']}"})
    assert me.status_code == 200
    assert me.json()["email"] == admin.email
    assert me.json()["role"] == "admin"


def test_login_works_for_reserved_domains_used_by_the_seed_accounts(client, db, dept):
    user = make_admin(db, dept, email="admin@hansraj.sentinelx.local")

    assert login(client, user.email, DEFAULT_PASSWORD).status_code == 200
    assert client.get(ME, headers=bearer(user)).status_code == 200


def test_every_kind_of_login_failure_looks_the_same(client, db, dept, admin):
    inactive = make_admin(db, dept, is_active=False)

    wrong_password = login(client, admin.email, "not-the-password")
    unknown_email = login(client, "nobody@example.com", DEFAULT_PASSWORD)
    malformed_email = login(client, "not-an-email", DEFAULT_PASSWORD)
    inactive_account = login(client, inactive.email, DEFAULT_PASSWORD)

    responses = [wrong_password, unknown_email, malformed_email, inactive_account]
    assert [r.status_code for r in responses] == [401, 401, 401, 401]
    assert all(r.json() == wrong_password.json() for r in responses)


def test_logins_are_audited_without_the_password(client, db, admin):
    login(client, admin.email, "not-the-password")
    login(client, admin.email, DEFAULT_PASSWORD)

    entries = db.execute(select(AuditLog).where(AuditLog.action.in_([AuditAction.LOGIN_FAILURE, AuditAction.LOGIN_SUCCESS]))).scalars().all()
    actions = {entry.action for entry in entries}

    assert actions == {AuditAction.LOGIN_FAILURE, AuditAction.LOGIN_SUCCESS}
    success = next(e for e in entries if e.action == AuditAction.LOGIN_SUCCESS)
    assert success.actor_id == admin.id
    for entry in entries:
        assert "not-the-password" not in str(entry.metadata_json)
        assert DEFAULT_PASSWORD not in str(entry.metadata_json)


def test_password_is_stored_as_a_bcrypt_hash(admin):
    assert admin.hashed_password != DEFAULT_PASSWORD
    assert admin.hashed_password.startswith("$2")
    assert verify_password(DEFAULT_PASSWORD, admin.hashed_password)
    assert not verify_password("something-else", admin.hashed_password)


def test_protected_route_needs_a_token(client):
    assert client.get(ME).status_code == 401


def test_garbage_token_is_rejected(client):
    assert client.get(ME, headers={"Authorization": "Bearer not-a-token"}).status_code == 401


def test_expired_token_is_rejected(client, admin):
    expired = _create_token(admin.id, "admin", TokenType.ACCESS, timedelta(seconds=-5))
    assert client.get(ME, headers={"Authorization": f"Bearer {expired}"}).status_code == 401


def test_token_signed_with_another_key_is_rejected(client, admin):
    from jose import jwt

    forged = jwt.encode(
        {"sub": str(admin.id), "role": "admin", "token_type": "access", "exp": 4102444800},
        "some-other-secret",
        algorithm="HS256",
    )
    assert client.get(ME, headers={"Authorization": f"Bearer {forged}"}).status_code == 401


def test_refresh_token_cannot_open_the_api(client, admin):
    refresh = create_refresh_token(admin.id, "admin")
    assert client.get(ME, headers={"Authorization": f"Bearer {refresh}"}).status_code == 401


def test_access_token_cannot_be_used_to_refresh(client, admin):
    access = create_access_token(admin.id, "admin")
    assert client.post(REFRESH, json={"refresh_token": access}).status_code == 401


def test_refresh_gives_a_new_working_access_token(client, admin):
    tokens = login(client, admin.email, DEFAULT_PASSWORD).json()

    refreshed = client.post(REFRESH, json={"refresh_token": tokens["refresh_token"]})

    assert refreshed.status_code == 200
    me = client.get(ME, headers={"Authorization": f"Bearer {refreshed.json()['access_token']}"})
    assert me.status_code == 200


def test_refresh_fails_once_the_account_is_deactivated(client, db, admin):
    tokens = login(client, admin.email, DEFAULT_PASSWORD).json()
    admin.is_active = False
    db.flush()

    assert client.post(REFRESH, json={"refresh_token": tokens["refresh_token"]}).status_code == 401


def test_deactivated_account_is_blocked_even_with_a_valid_token(client, db, admin):
    headers = bearer(admin)
    assert client.get(ME, headers=headers).status_code == 200

    admin.is_active = False
    db.flush()

    assert client.get(ME, headers=headers).status_code == 403


def test_errors_use_the_documented_json_shape(client):
    response = client.get(ME)

    assert response.status_code == 401
    assert set(response.json()["error"]) == {"message", "status_code"}