"""GET /findings: the department-wide findings list used by the All findings page."""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.models.enums import FindingStatus, Severity
from tests import factories
from tests.factories import POC_TEXT, RAW_OUTPUT_TEXT, bearer

API = "/api/v1"
NOW = datetime.now(timezone.utc)


@pytest.fixture()
def world(db, dept, vendor_a):
    site_a = factories.make_site(db, dept, vendor=vendor_a, name="Site A")
    site_b = factories.make_site(db, dept, name="Site B")

    def add(site, status, severity, endpoint, age_days):
        finding = factories.make_finding(db, site, status=status, severity=severity, endpoint=endpoint)
        finding.created_at = NOW - timedelta(days=age_days)  # explicit times, so the order is not a tie
        db.flush()
        return finding

    return SimpleNamespace(
        site_a=site_a,
        site_b=site_b,
        oldest=add(site_a, FindingStatus.APPROVED, Severity.HIGH, "/a1", 5),
        newest=add(site_a, FindingStatus.DISCARDED, Severity.LOW, "/a2", 1),
        pending=add(site_a, FindingStatus.PENDING_ADMIN_REVIEW, Severity.CRITICAL, "/a3", 3),
        other_site=add(site_b, FindingStatus.REJECTED, Severity.MEDIUM, "/b1", 2),
    )


def ids(response):
    return [item["id"] for item in response.json()]


def test_lists_every_finding_newest_first_whatever_its_status(client, admin, world):
    response = client.get(f"{API}/findings", headers=bearer(admin))

    assert response.status_code == 200
    assert ids(response) == [
        str(world.newest.id), str(world.other_site.id), str(world.pending.id), str(world.oldest.id),
    ]


def test_can_be_filtered_by_site(client, admin, world):
    response = client.get(f"{API}/findings?site_id={world.site_b.id}", headers=bearer(admin))

    assert ids(response) == [str(world.other_site.id)]


def test_can_be_filtered_by_status(client, admin, world):
    response = client.get(f"{API}/findings?status=approved", headers=bearer(admin))

    assert ids(response) == [str(world.oldest.id)]


def test_site_and_status_filters_combine(client, admin, world):
    response = client.get(f"{API}/findings?site_id={world.site_a.id}&status=rejected", headers=bearer(admin))

    assert ids(response) == []


def test_an_unknown_status_is_rejected(client, admin):
    assert client.get(f"{API}/findings?status=bogus", headers=bearer(admin)).status_code == 422


def test_another_departments_findings_never_appear(client, db, admin, world):
    outsider_department = factories.make_department(db)
    outsider_site = factories.make_site(db, outsider_department)
    outsider = factories.make_finding(db, outsider_site)

    everything = client.get(f"{API}/findings", headers=bearer(admin))
    by_foreign_site = client.get(f"{API}/findings?site_id={outsider_site.id}", headers=bearer(admin))

    assert str(outsider.id) not in ids(everything)
    assert ids(by_foreign_site) == []


def test_the_list_carries_no_proof_or_scanner_output(client, admin, world):
    response = client.get(f"{API}/findings", headers=bearer(admin))

    for item in response.json():
        assert set(item) == {
            "id", "site_id", "title", "severity", "status", "affected_endpoint", "confidence", "created_at",
        }
    assert POC_TEXT not in response.text
    assert RAW_OUTPUT_TEXT not in response.text


def test_pending_review_is_still_reachable_next_to_the_list(client, admin, world):
    response = client.get(f"{API}/findings/pending-review", headers=bearer(admin))

    assert response.status_code == 200
    assert [item["id"] for item in response.json()] == [str(world.pending.id)]


def test_vendors_and_signed_out_callers_are_refused(client, vendor_a_user):
    assert client.get(f"{API}/findings", headers=bearer(vendor_a_user)).status_code == 403
    assert client.get(f"{API}/findings").status_code == 401