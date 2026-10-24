"""Login hardening: throttling after repeated failures, and no timing clue
about which emails exist."""
from datetime import timedelta

from sqlalchemy import func, select, update

from app.models.audit_log import AuditLog
from app.models.enums import AuditAction
from app.services import audit_service, auth_service, rate_limit_service
from tests.factories import DEFAULT_PASSWORD, make_admin

LOGIN = "/api/v1/auth/login"
CLIENT_IP = "testclient"  # what Starlette's test client reports


def attempt(client, email, password):
    return client.post(LOGIN, json={"email": email, "password": password})


def add_failures(db, email, count, ip=CLIENT_IP):
    for _ in range(count):
        audit_service.record(
            db,
            action=AuditAction.LOGIN_FAILURE,
            entity_type="user",
            metadata={"email": rate_limit_service.normalize_email(email), "ip": ip},
        )
    db.flush()


def add_success(db, email):
    audit_service.record(
        db,
        action=AuditAction.LOGIN_SUCCESS,
        entity_type="user",
        metadata={"email": rate_limit_service.normalize_email(email)},
    )
    db.flush()


def age_everything(db, minutes):
    db.execute(
        update(AuditLog)
        .values(timestamp=AuditLog.timestamp - timedelta(minutes=minutes))
        .execution_options(synchronize_session=False)
    )
    db.flush()


def failure_count(db):
    return db.execute(
        select(func.count(AuditLog.id)).where(AuditLog.action == AuditAction.LOGIN_FAILURE)
    ).scalar_one()


# ---- Per address ----

def test_the_sixth_attempt_is_blocked_even_with_the_right_password(client, db, admin):
    for _ in range(5):
        assert attempt(client, admin.email, "wrong").status_code == 401

    blocked = attempt(client, admin.email, DEFAULT_PASSWORD)

    assert blocked.status_code == 429
    assert "Try again in" in blocked.json()["error"]["message"]
    assert 1 <= int(blocked.headers["Retry-After"]) <= 900
    assert failure_count(db) == 5  # a blocked attempt is not counted, so it cannot extend the lock


def test_four_failures_do_not_block(client, db, admin):
    add_failures(db, admin.email, 4)

    assert attempt(client, admin.email, DEFAULT_PASSWORD).status_code == 200


def test_an_unknown_address_is_blocked_the_same_way(client, db, admin):
    add_failures(db, "nobody@example.com", 5)
    add_failures(db, admin.email, 5)

    unknown = attempt(client, "nobody@example.com", "anything")
    known = attempt(client, admin.email, DEFAULT_PASSWORD)

    assert unknown.status_code == known.status_code == 429
    assert unknown.json()["error"]["message"] == known.json()["error"]["message"]


def test_capital_letters_and_spaces_share_one_count(client, db, admin):
    add_failures(db, admin.email.upper(), 3)
    add_failures(db, f"  {admin.email}  ", 2)

    assert attempt(client, admin.email, DEFAULT_PASSWORD).status_code == 429


def test_other_accounts_are_not_affected(client, db, dept, admin):
    colleague = make_admin(db, dept)
    add_failures(db, admin.email, 5)

    assert attempt(client, admin.email, DEFAULT_PASSWORD).status_code == 429
    assert attempt(client, colleague.email, DEFAULT_PASSWORD).status_code == 200


def test_the_block_lifts_after_the_window(client, db, admin):
    add_failures(db, admin.email, 5)
    age_everything(db, 20)

    assert attempt(client, admin.email, DEFAULT_PASSWORD).status_code == 200


def test_the_wait_shrinks_as_failures_age(db, admin):
    add_failures(db, admin.email, 5)
    age_everything(db, 10)

    wait = rate_limit_service.seconds_until_allowed(db, rate_limit_service.normalize_email(admin.email), None)

    assert 200 < wait <= 300  # the oldest failure leaves the 15 minute window in about 5 minutes


def test_a_successful_login_clears_the_earlier_failures(client, db, admin):
    add_failures(db, admin.email, 4)
    age_everything(db, 2)
    add_success(db, admin.email)
    add_failures(db, admin.email, 4)  # four more since the success: 4 in total would block without the reset

    assert attempt(client, admin.email, DEFAULT_PASSWORD).status_code == 200


def test_five_failures_since_a_success_do_block(client, db, admin):
    add_failures(db, admin.email, 4)
    age_everything(db, 2)
    add_success(db, admin.email)
    add_failures(db, admin.email, 5)

    assert attempt(client, admin.email, DEFAULT_PASSWORD).status_code == 429


# ---- Per client address ----

def test_twenty_failures_from_one_ip_block_any_account(client, db, admin):
    for number in range(20):
        add_failures(db, f"person{number}@example.com", 1)

    assert attempt(client, admin.email, DEFAULT_PASSWORD).status_code == 429


def test_nineteen_failures_from_one_ip_do_not_block(client, db, admin):
    for number in range(19):
        add_failures(db, f"person{number}@example.com", 1)

    assert attempt(client, admin.email, DEFAULT_PASSWORD).status_code == 200


def test_failures_from_another_ip_do_not_count(client, db, admin):
    for number in range(20):
        add_failures(db, f"person{number}@example.com", 1, ip="203.0.113.7")

    assert attempt(client, admin.email, DEFAULT_PASSWORD).status_code == 200


def test_a_failure_is_recorded_with_the_address_and_ip_but_never_the_password(client, db, admin):
    attempt(client, f"  {admin.email.upper()}  ", "my-secret-guess")

    entry = db.execute(select(AuditLog).where(AuditLog.action == AuditAction.LOGIN_FAILURE)).scalar_one()
    assert entry.metadata_json == {"email": admin.email.lower(), "ip": CLIENT_IP}
    assert "my-secret-guess" not in str(entry.metadata_json)


# ---- Timing ----

def test_an_unknown_email_still_gets_a_password_check(client, db, admin, monkeypatch):
    checked = []

    def spy(password, hashed):
        checked.append(hashed)
        return False

    monkeypatch.setattr(auth_service, "verify_password", spy)

    attempt(client, "nobody@example.com", "anything")
    attempt(client, admin.email, "anything")

    assert checked == [auth_service._dummy_hash(), admin.hashed_password]  # noqa: SLF001