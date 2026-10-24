"""Role-based access control, vendor isolation and department isolation.

The SRS requires these rules to be enforced by the backend, not only hidden in
the frontend, so every check here goes through the real HTTP API.
"""
import uuid
from types import SimpleNamespace

import pytest
from sqlalchemy import func, select

from app.models.enums import FindingStatus, TicketStatus
from app.models.ticket import RemediationSubmission
from tests.factories import (
    DEFAULT_PASSWORD,
    POC_TEXT,
    RAW_OUTPUT_TEXT,
    bearer,
    make_admin,
    make_alert,
    make_department,
    make_finding,
    make_site,
    make_ticket,
    make_vendor,
    make_vendor_user,
)

API = "/api/v1"
BODY_METHODS = {"POST", "PUT", "PATCH"}

ADMIN_ONLY = [
    ("GET", "/sites"),
    ("POST", "/sites"),
    ("GET", "/sites/{id}"),
    ("PATCH", "/sites/{id}/schedule"),
    ("PATCH", "/sites/{id}/exclusions"),
    ("PATCH", "/sites/{id}/vendor"),
    ("PATCH", "/sites/{id}/active"),
    ("GET", "/sites/{id}/authorization-records"),
    ("POST", "/sites/{id}/authorization-records"),
    ("GET", "/vendors"),
    ("POST", "/vendors"),
    ("PATCH", "/vendors/{id}"),
    ("DELETE", "/vendors/{id}"),
    ("GET", "/scans"),
    ("POST", "/scans/{id}/trigger"),
    ("GET", "/scans/{id}"),
    ("GET", "/scans/{id}/executions"),
    ("GET", "/agent-executions/{id}"),
    ("GET", "/findings/pending-review"),
    ("GET", "/findings/{id}"),
    ("POST", "/findings/{id}/review"),
    ("GET", "/tickets"),
    ("GET", "/tickets/{id}"),
    ("POST", "/tickets/{id}/assign"),
    ("GET", "/alerts"),
    ("GET", "/scorecards/{id}"),
    ("GET", "/schedules/sla"),
    ("PUT", "/schedules/sla"),
    ("POST", "/users"),
    ("GET", "/users/vendor/{id}"),
]

VENDOR_ONLY = [
    ("GET", "/tickets/mine"),
    ("GET", "/tickets/mine/{id}"),
    ("POST", "/tickets/mine/{id}/remediate"),
    ("GET", "/alerts/mine"),
    ("GET", "/scorecards/mine"),
]

ANY_ROLE = [
    ("GET", "/users/me"),
    ("PATCH", "/users/me/preferences"),
    ("GET", "/vendors/{id}"),
]


def call(client, method: str, path: str, headers: dict | None = None):
    url = API + path.replace("{id}", str(uuid.uuid4()))
    if method in BODY_METHODS:
        return client.request(method, url, headers=headers, json={})
    return client.request(method, url, headers=headers)


def ids_of(response) -> set[str]:
    return {item["id"] for item in response.json()}


def endpoint_ids(endpoints):
    return [f"{method} {path}" for method, path in endpoints]


# ---- Roles on every endpoint ----

@pytest.mark.parametrize("method,path", ADMIN_ONLY + VENDOR_ONLY + ANY_ROLE, ids=endpoint_ids(ADMIN_ONLY + VENDOR_ONLY + ANY_ROLE))
def test_signed_out_requests_are_rejected(client, method, path):
    assert call(client, method, path).status_code == 401


@pytest.mark.parametrize("method,path", ADMIN_ONLY, ids=endpoint_ids(ADMIN_ONLY))
def test_vendor_cannot_use_admin_endpoints(client, vendor_a_user, method, path):
    assert call(client, method, path, bearer(vendor_a_user)).status_code == 403


@pytest.mark.parametrize("method,path", VENDOR_ONLY, ids=endpoint_ids(VENDOR_ONLY))
def test_admin_cannot_use_vendor_endpoints(client, admin, method, path):
    assert call(client, method, path, bearer(admin)).status_code == 403


# ---- Vendor isolation ----

@pytest.fixture()
def world(db, dept, vendor_a, vendor_b, vendor_a_user, vendor_b_user):
    site_a = make_site(db, dept, vendor=vendor_a, name="Site A")
    site_b = make_site(db, dept, vendor=vendor_b, name="Site B")
    finding_a = make_finding(db, site_a, status=FindingStatus.APPROVED)
    finding_b = make_finding(db, site_b, status=FindingStatus.APPROVED, endpoint="/vulnerabilities/sqli/")
    ticket_a = make_ticket(db, finding_a, vendor_a)
    ticket_b = make_ticket(db, finding_b, vendor_b)
    alert_a = make_alert(db, vendor_a_user, site=site_a, ticket=ticket_a)
    alert_b = make_alert(db, vendor_b_user, site=site_b, ticket=ticket_b)
    return SimpleNamespace(
        site_a=site_a, site_b=site_b, ticket_a=ticket_a, ticket_b=ticket_b, alert_a=alert_a, alert_b=alert_b
    )


def test_vendor_lists_only_their_own_tickets(client, vendor_a_user, world):
    response = client.get(f"{API}/tickets/mine", headers=bearer(vendor_a_user))

    assert response.status_code == 200
    assert ids_of(response) == {str(world.ticket_a.id)}


def test_vendor_cannot_open_another_vendors_ticket(client, vendor_a_user, world):
    response = client.get(f"{API}/tickets/mine/{world.ticket_b.id}", headers=bearer(vendor_a_user))

    assert response.status_code == 403


def test_vendor_cannot_submit_a_fix_for_another_vendors_ticket(client, db, vendor_a_user, world, task_calls):
    response = client.post(
        f"{API}/tickets/mine/{world.ticket_b.id}/remediate",
        headers=bearer(vendor_a_user),
        json={"note": "I fixed it."},
    )

    assert response.status_code == 403
    db.refresh(world.ticket_b)
    assert world.ticket_b.status == TicketStatus.OPEN
    submissions = db.execute(
        select(func.count(RemediationSubmission.id)).where(RemediationSubmission.ticket_id == world.ticket_b.id)
    ).scalar_one()
    assert submissions == 0
    assert task_calls == []


def test_vendor_can_submit_a_fix_for_their_own_ticket(client, vendor_a_user, world, task_calls):
    response = client.post(
        f"{API}/tickets/mine/{world.ticket_a.id}/remediate",
        headers=bearer(vendor_a_user),
        json={"note": "Upgraded the library."},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "fix_submitted_pending_verification"
    assert task_calls == [("app.tasks.verification_tasks.run_verification_scan", (str(world.ticket_a.id),))]


def test_vendor_view_of_a_ticket_has_no_exploit_or_internal_detail(client, vendor_a_user, world):
    response = client.get(f"{API}/tickets/mine/{world.ticket_a.id}", headers=bearer(vendor_a_user))

    assert response.status_code == 200
    internal_fields = {
        "poc_summary",
        "raw_scanner_output",
        "raw_scanner_output_encrypted",
        "poc_summary_encrypted",
        "override_reason",
        "suggested_deadline",
        "finding_id",
        "vendor_id",
    }
    assert internal_fields.isdisjoint(response.json())
    assert POC_TEXT not in response.text
    assert RAW_OUTPUT_TEXT not in response.text


def test_vendor_reads_only_their_own_vendor_record(client, vendor_a_user, vendor_a, vendor_b):
    own = client.get(f"{API}/vendors/{vendor_a.id}", headers=bearer(vendor_a_user))
    other = client.get(f"{API}/vendors/{vendor_b.id}", headers=bearer(vendor_a_user))

    assert own.status_code == 200
    assert other.status_code == 403


def test_vendor_sees_only_their_own_alerts(client, vendor_a_user, world):
    response = client.get(f"{API}/alerts/mine", headers=bearer(vendor_a_user))

    assert response.status_code == 200
    assert ids_of(response) == {str(world.alert_a.id)}


def test_vendor_scorecard_is_their_own(client, vendor_a_user, vendor_a, world):
    response = client.get(f"{API}/scorecards/mine", headers=bearer(vendor_a_user))

    assert response.status_code == 200
    assert response.json()["vendor_id"] == str(vendor_a.id)


def test_vendor_cannot_read_another_vendors_scorecard(client, vendor_a_user, vendor_b, world):
    response = client.get(f"{API}/scorecards/{vendor_b.id}", headers=bearer(vendor_a_user))

    assert response.status_code == 403


# ---- Department isolation ----

@pytest.fixture()
def other_department(db):
    department = make_department(db)
    vendor = make_vendor(db, department)
    site = make_site(db, department, vendor=vendor)
    pending_finding = make_finding(db, site)
    approved_finding = make_finding(db, site, status=FindingStatus.APPROVED, endpoint="/other")
    ticket = make_ticket(db, approved_finding, vendor)
    return SimpleNamespace(
        vendor=vendor, site=site, pending_finding=pending_finding, ticket=ticket
    )


def test_admin_lists_exclude_other_departments(client, admin, world, other_department):
    headers = bearer(admin)

    sites = client.get(f"{API}/sites", headers=headers)
    vendors = client.get(f"{API}/vendors", headers=headers)
    tickets = client.get(f"{API}/tickets", headers=headers)
    pending = client.get(f"{API}/findings/pending-review", headers=headers)

    assert str(other_department.site.id) not in ids_of(sites)
    assert str(world.site_a.id) in ids_of(sites)
    assert str(other_department.vendor.id) not in ids_of(vendors)
    assert str(other_department.ticket.id) not in ids_of(tickets)
    assert str(other_department.pending_finding.id) not in ids_of(pending)


def test_admin_cannot_open_other_departments_records(client, admin, other_department):
    headers = bearer(admin)
    paths = [
        f"/sites/{other_department.site.id}",
        f"/vendors/{other_department.vendor.id}",
        f"/tickets/{other_department.ticket.id}",
        f"/findings/{other_department.pending_finding.id}",
        f"/scorecards/{other_department.vendor.id}",
    ]

    assert [client.get(API + path, headers=headers).status_code for path in paths] == [404] * len(paths)


def test_admin_cannot_change_other_departments_records(client, db, admin, vendor_a, other_department, task_calls):
    headers = bearer(admin)

    review = client.post(
        f"{API}/findings/{other_department.pending_finding.id}/review", headers=headers, json={"decision": "approve"}
    )
    assign = client.post(
        f"{API}/tickets/{other_department.ticket.id}/assign", headers=headers, json={"vendor_id": str(vendor_a.id)}
    )
    scan = client.post(f"{API}/scans/{other_department.site.id}/trigger", headers=headers, json={})

    assert [review.status_code, assign.status_code, scan.status_code] == [404, 404, 404]
    db.refresh(other_department.pending_finding)
    assert other_department.pending_finding.status == FindingStatus.PENDING_ADMIN_REVIEW
    assert task_calls == []


# ---- Account creation keeps the two-role model ----

def new_login(vendor_id=None, **overrides):
    body = {
        "email": "new.person@example.com",
        "password": "LongEnough1",
        "full_name": "New Person",
        "role": "vendor",
        "vendor_id": str(vendor_id) if vendor_id is not None else None,
    }
    body.update(overrides)
    return body


def test_admin_creates_a_vendor_login_that_can_sign_in(client, admin, vendor_a):
    created = client.post(f"{API}/users", headers=bearer(admin), json=new_login(vendor_a.id))
    assert created.status_code == 201
    assert created.json()["role"] == "vendor"
    assert created.json()["vendor_id"] == str(vendor_a.id)
    assert "password" not in created.text

    signed_in = client.post(f"{API}/auth/login", json={"email": "new.person@example.com", "password": "LongEnough1"})
    assert signed_in.status_code == 200
    me = client.get(f"{API}/users/me", headers={"Authorization": f"Bearer {signed_in.json()['access_token']}"})
    assert me.json()["role"] == "vendor"


def test_admin_cannot_create_another_admin_account(client, admin):
    response = client.post(f"{API}/users", headers=bearer(admin), json=new_login(role="admin"))

    assert response.status_code == 400


def test_vendor_login_needs_a_long_enough_password(client, admin, vendor_a):
    response = client.post(f"{API}/users", headers=bearer(admin), json=new_login(vendor_a.id, password="short"))

    assert response.status_code == 400


def test_vendor_login_email_must_be_new(client, db, dept, admin, vendor_a):
    existing = make_vendor_user(db, vendor_a)

    response = client.post(f"{API}/users", headers=bearer(admin), json=new_login(vendor_a.id, email=existing.email))

    assert response.status_code == 409


def test_vendor_login_cannot_be_attached_to_another_departments_vendor(client, admin, other_department):
    response = client.post(f"{API}/users", headers=bearer(admin), json=new_login(other_department.vendor.id))

    assert response.status_code == 404


def test_default_test_password_is_not_reused_by_accident(db, dept):
    # Guards the fixtures: a custom password must really be hashed on its own.
    from app.core.security import verify_password

    user = make_admin(db, dept, password="A-different-password-1")

    assert verify_password("A-different-password-1", user.hashed_password)
    assert not verify_password(DEFAULT_PASSWORD, user.hashed_password)