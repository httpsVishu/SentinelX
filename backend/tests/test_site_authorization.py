"""The IT Act rule: no scan of a restricted site without a written authorization
on file. Also site input validation and the schedule and exclusion settings."""
import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import select

from app.models.authorization_record import AuthorizationRecord
from app.models.enums import AuditAction, ScanStatus
from app.models.scan import Scan
from app.services.authorization_service import url_is_restricted_domain
from tests import factories
from tests.factories import bearer
from tests.lifecycle.helpers import audit_actions

API = "/api/v1"
EXECUTE = "app.tasks.scan_tasks.execute_scan"
GOV_URL = "https://portal.example.gov.in"


def trigger(client, admin, site):
    return client.post(f"{API}/scans/{site.id}/trigger", headers=bearer(admin), json={})


def scans_of(db, site):
    return list(db.execute(select(Scan).where(Scan.site_id == site.id)).scalars())


# ---- Which addresses count as restricted ----

@pytest.mark.parametrize(
    "url,expected",
    [
        ("https://portal.example.gov.in", True),
        ("https://portal.GOV.IN/login", True),
        ("https://portal.gov.in:8443/admin", True),
        ("http://juice-shop.local:3000", False),
        ("https://notgov.in", False),
        ("https://example.com/gov.in", False),
        ("https://portal.gov.in.example.com", False),
        ("not a url", False),
    ],
)
def test_which_addresses_are_restricted(url, expected):
    assert url_is_restricted_domain(url) is expected


# ---- The scan gate ----

def test_a_restricted_site_cannot_be_scanned_without_authorization(client, db, dept, admin, task_calls):
    site = factories.make_site(db, dept, url=GOV_URL, is_gov_in=True)

    response = trigger(client, admin, site)

    assert response.status_code == 403
    assert "authorization" in response.json()["error"]["message"].lower()
    assert scans_of(db, site) == []
    assert task_calls == []


def test_a_gov_in_address_is_enough_even_when_the_flag_was_not_set(client, db, dept, admin, task_calls):
    site = factories.make_site(db, dept, url=GOV_URL, is_gov_in=False)

    assert trigger(client, admin, site).status_code == 403
    assert task_calls == []


def test_recording_an_authorization_unlocks_scanning(client, db, dept, admin, task_calls):
    site = factories.make_site(db, dept, url=GOV_URL, is_gov_in=True)

    added = client.post(
        f"{API}/sites/{site.id}/authorization-records",
        headers=bearer(admin),
        json={
            "document_reference": "Letter 12/2026",
            "notes": "Signed by the registrar.",
            "granted_at": "2026-10-01T00:00:00+00:00",
        },
    )
    assert added.status_code == 201
    assert added.json()["granted_by_user_id"] == str(admin.id)
    assert AuditAction.AUTHORIZATION_RECORD_ADDED in audit_actions(db, site.id)

    listed = client.get(f"{API}/sites/{site.id}/authorization-records", headers=bearer(admin))
    assert [r["document_reference"] for r in listed.json()] == ["Letter 12/2026"]

    response = trigger(client, admin, site)
    assert response.status_code == 201
    assert task_calls == [(EXECUTE, (response.json()["id"],))]


def test_an_authorization_needs_a_document_reference(client, db, dept, admin):
    site = factories.make_site(db, dept, url=GOV_URL, is_gov_in=True)

    response = client.post(
        f"{API}/sites/{site.id}/authorization-records",
        headers=bearer(admin),
        json={"document_reference": "", "granted_at": "2026-10-01T00:00:00+00:00"},
    )

    assert response.status_code == 422


def test_an_ordinary_site_needs_no_authorization(client, db, dept, vendor_a, admin, task_calls):
    site = factories.make_site(db, dept, vendor=vendor_a, url="http://juice-shop.local:3000")

    assert trigger(client, admin, site).status_code == 201
    assert len(task_calls) == 1


def test_a_site_without_a_vendor_can_still_be_scanned(client, db, dept, admin):
    site = factories.make_site(db, dept, vendor=None)

    assert trigger(client, admin, site).status_code == 201


def test_a_paused_site_cannot_be_scanned_until_it_is_resumed(client, db, dept, admin, task_calls):
    site = factories.make_site(db, dept)

    paused = client.patch(f"{API}/sites/{site.id}/active", headers=bearer(admin), json={"is_active": False})
    assert paused.status_code == 200
    assert trigger(client, admin, site).status_code == 409
    assert scans_of(db, site) == []
    assert task_calls == []

    client.patch(f"{API}/sites/{site.id}/active", headers=bearer(admin), json={"is_active": True})
    assert trigger(client, admin, site).status_code == 201


# ---- Creating sites ----

def test_a_site_on_a_gov_in_address_is_flagged_automatically(client, admin):
    created = client.post(
        f"{API}/sites", headers=bearer(admin), json={"name": "Portal", "url": GOV_URL, "is_gov_in": False}
    )

    assert created.status_code == 201
    assert created.json()["is_gov_in"] is True


@pytest.mark.parametrize(
    "body",
    [
        {"name": "Site", "url": "ftp://files.example.com"},
        {"name": "Site", "url": "juice-shop.local"},
        {"name": "", "url": "http://a.local"},
        {"name": "Site", "url": "http://a.local", "scan_frequency_days": 0},
        {"name": "Site", "url": "http://a.local", "scan_frequency_days": 366},
    ],
)
def test_site_input_is_validated(client, admin, body):
    assert client.post(f"{API}/sites", headers=bearer(admin), json=body).status_code == 422


# ---- Schedule and exclusions ----

def test_changing_the_schedule_does_not_cancel_a_running_scan(client, db, dept, vendor_a, admin):
    site = factories.make_site(db, dept, vendor=vendor_a)
    running = factories.make_scan(db, site, status=ScanStatus.RUNNING)

    response = client.patch(
        f"{API}/sites/{site.id}/schedule", headers=bearer(admin), json={"scan_frequency_days": 14}
    )

    assert response.status_code == 200
    db.refresh(running)
    db.refresh(site)
    assert running.status == ScanStatus.RUNNING
    assert running.completed_at is None
    assert site.scan_frequency_days == 14
    assert AuditAction.SITE_SCHEDULE_UPDATED in audit_actions(db, site.id)


@pytest.mark.parametrize("days", [0, 366])
def test_the_schedule_must_be_a_sensible_number_of_days(client, db, dept, admin, days):
    site = factories.make_site(db, dept)

    response = client.patch(f"{API}/sites/{site.id}/schedule", headers=bearer(admin), json={"scan_frequency_days": days})

    assert response.status_code == 422


def test_exclusions_are_saved_and_audited(client, db, dept, admin):
    site = factories.make_site(db, dept)

    response = client.patch(
        f"{API}/sites/{site.id}/exclusions", headers=bearer(admin), json={"excluded_paths": ["/admin", "/internal"]}
    )

    assert response.status_code == 200
    assert response.json()["excluded_paths"] == ["/admin", "/internal"]
    assert AuditAction.SITE_EXCLUSIONS_UPDATED in audit_actions(db, site.id)


def test_a_vendor_can_be_mapped_to_a_site_and_must_belong_to_the_department(client, db, dept, admin, vendor_a):
    site = factories.make_site(db, dept)
    outsider = factories.make_vendor(db, factories.make_department(db))

    mapped = client.patch(f"{API}/sites/{site.id}/vendor", headers=bearer(admin), json={"vendor_id": str(vendor_a.id)})
    refused = client.patch(f"{API}/sites/{site.id}/vendor", headers=bearer(admin), json={"vendor_id": str(outsider.id)})

    assert mapped.status_code == 200
    assert mapped.json()["vendor_id"] == str(vendor_a.id)
    assert refused.status_code == 400


# ---- Audit actions for creating records ----

def test_creating_a_site_is_logged_as_a_site_creation(client, db, admin):
    response = client.post(
        f"{API}/sites", headers=bearer(admin), json={"name": "Portal", "url": "http://portal.example.com"}
    )

    assert response.status_code in (200, 201)
    site_id = uuid.UUID(response.json()["id"])
    actions = audit_actions(db, site_id)
    assert AuditAction.SITE_CREATED in actions
    assert AuditAction.SITE_SCHEDULE_UPDATED not in actions


def test_creating_a_vendor_is_logged_as_a_vendor_creation(client, db, admin):
    response = client.post(
        f"{API}/vendors", headers=bearer(admin), json={"name": "Acme Web", "contact_email": "ops@acme.example.com"}
    )

    assert response.status_code in (200, 201)
    vendor_id = uuid.UUID(response.json()["id"])
    actions = audit_actions(db, vendor_id)
    assert AuditAction.VENDOR_CREATED in actions
    assert AuditAction.TICKET_VENDOR_ASSIGNED not in actions