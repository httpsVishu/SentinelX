"""Duplicate scan prevention, scan waiting and failure, and scheduled dispatch."""
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from celery.exceptions import Retry
from sqlalchemy import select

from app.models.audit_log import AuditLog
from app.models.authorization_record import AuthorizationRecord
from app.models.enums import AuditAction, ScanStatus, ScanTriggerType
from app.models.scan import Scan
from tests import factories
from tests.factories import bearer

API = "/api/v1"
EXECUTE = "app.tasks.scan_tasks.execute_scan"
NOTIFY = "app.tasks.notification_tasks.notify_scan_failed"


@pytest.fixture()
def site(db, dept, vendor_a):
    return factories.make_site(db, dept, vendor=vendor_a, name="Juice Shop", url="http://juice-shop.local:3000")


@pytest.fixture()
def pipeline_calls(monkeypatch):
    """Replaces the scan graph. These tests are about queueing, not scanning."""
    calls = []

    def fake_pipeline(db, scan_id, site, scope_paths=None):
        calls.append(scan_id)

    monkeypatch.setattr("app.tasks.scan_tasks.run_scan_pipeline", fake_pipeline)
    return calls


def run_scan(scan):
    from app.tasks.scan_tasks import execute_scan

    execute_scan(str(scan.id))


def queued_site_ids(db):
    return set(db.execute(select(Scan.site_id).where(Scan.status == ScanStatus.QUEUED)).scalars())


def trigger_entry(db, scan_id):
    return db.execute(
        select(AuditLog).where(AuditLog.entity_id == uuid.UUID(scan_id), AuditLog.entity_type == "scan")
    ).scalar_one()


# ---- Triggering while a scan is already in flight ----

def test_a_second_manual_scan_is_queued_behind_the_first(client, db, admin, site, task_calls):
    first = client.post(f"{API}/scans/{site.id}/trigger", headers=bearer(admin), json={})
    second = client.post(f"{API}/scans/{site.id}/trigger", headers=bearer(admin), json={})

    assert [first.status_code, second.status_code] == [201, 201]
    assert {first.json()["status"], second.json()["status"]} == {"queued"}
    assert first.json()["id"] != second.json()["id"]
    assert task_calls == [(EXECUTE, (first.json()["id"],)), (EXECUTE, (second.json()["id"],))]

    first_entry = trigger_entry(db, first.json()["id"])
    second_entry = trigger_entry(db, second.json()["id"])
    assert first_entry.action == AuditAction.SCAN_TRIGGERED
    assert first_entry.metadata_json["queued_behind_running_scan"] is False
    assert second_entry.action == AuditAction.SCAN_QUEUED_DUPLICATE
    assert second_entry.metadata_json["queued_behind_running_scan"] is True
    assert second_entry.actor_id == admin.id


# ---- The worker serializes scans per site ----

def test_a_queued_scan_waits_while_another_scan_of_the_site_is_running(db, site, pipeline_calls):
    running = factories.make_scan(db, site, status=ScanStatus.RUNNING)
    queued = factories.make_scan(db, site, status=ScanStatus.QUEUED, trigger=ScanTriggerType.MANUAL)

    with pytest.raises(Retry):
        run_scan(queued)

    db.refresh(queued)
    db.refresh(running)
    assert queued.status == ScanStatus.QUEUED
    assert running.status == ScanStatus.RUNNING
    assert pipeline_calls == []


def test_the_waiting_scan_runs_once_the_first_one_has_finished(db, site, pipeline_calls):
    running = factories.make_scan(db, site, status=ScanStatus.RUNNING)
    queued = factories.make_scan(db, site, status=ScanStatus.QUEUED, trigger=ScanTriggerType.MANUAL)
    with pytest.raises(Retry):
        run_scan(queued)

    running.status = ScanStatus.COMPLETED
    db.flush()
    run_scan(queued)

    db.refresh(queued)
    assert queued.status == ScanStatus.COMPLETED
    assert pipeline_calls == [queued.id]


def test_scans_of_different_sites_do_not_wait_for_each_other(db, dept, vendor_b, site, pipeline_calls):
    other = factories.make_site(db, dept, vendor=vendor_b, url="http://dvwa.local:8080")
    factories.make_scan(db, other, status=ScanStatus.RUNNING)
    queued = factories.make_scan(db, site, status=ScanStatus.QUEUED)

    run_scan(queued)

    db.refresh(queued)
    assert queued.status == ScanStatus.COMPLETED
    assert pipeline_calls == [queued.id]


def test_a_scan_that_waits_too_long_is_failed_visibly(db, site, pipeline_calls, monkeypatch, task_calls):
    from app.tasks.scan_tasks import execute_scan

    monkeypatch.setattr(execute_scan, "max_retries", 0)  # skip straight to the last attempt
    factories.make_scan(db, site, status=ScanStatus.RUNNING)
    queued = factories.make_scan(db, site, status=ScanStatus.QUEUED, trigger=ScanTriggerType.MANUAL)

    run_scan(queued)

    db.refresh(queued)
    assert queued.status == ScanStatus.FAILED
    assert "never started" in queued.error_message
    assert queued.completed_at is not None
    assert pipeline_calls == []
    assert task_calls == [(NOTIFY, (str(site.id), str(queued.id), queued.error_message))]


@pytest.mark.parametrize("status", [ScanStatus.COMPLETED, ScanStatus.FAILED, ScanStatus.RUNNING])
def test_a_scan_that_was_already_handled_is_not_run_again(db, site, pipeline_calls, status):
    scan = factories.make_scan(db, site, status=status)

    run_scan(scan)

    db.refresh(scan)
    assert scan.status == status
    assert pipeline_calls == []


def test_the_worker_refuses_to_scan_a_restricted_site_without_authorization(db, dept, pipeline_calls, task_calls):
    site = factories.make_site(db, dept, url="https://portal.example.gov.in", is_gov_in=True)
    scan = factories.make_scan(db, site, status=ScanStatus.QUEUED)  # created behind the API's back

    run_scan(scan)

    db.refresh(scan)
    assert scan.status == ScanStatus.FAILED
    assert "authorization" in scan.error_message.lower()
    assert pipeline_calls == []
    assert task_calls == [(NOTIFY, (str(site.id), str(scan.id), scan.error_message))]


# ---- Scheduled dispatch ----

def dispatch():
    from app.tasks.scan_tasks import dispatch_due_scheduled_scans

    dispatch_due_scheduled_scans()


def test_the_hourly_check_queues_only_the_sites_that_are_due(db, dept, vendor_a, task_calls):
    now = datetime.now(timezone.utc)
    never_scanned = factories.make_site(db, dept, vendor=vendor_a, name="Never scanned")
    stale = factories.make_site(db, dept, vendor=vendor_a, name="Stale", last_scanned_at=now - timedelta(days=8))
    factories.make_site(db, dept, vendor=vendor_a, name="Fresh", last_scanned_at=now - timedelta(days=2))
    factories.make_site(db, dept, vendor=vendor_a, name="Paused", is_active=False)
    busy = factories.make_site(db, dept, vendor=vendor_a, name="Busy", last_scanned_at=now - timedelta(days=30))
    factories.make_scan(db, busy, status=ScanStatus.RUNNING)

    dispatch()

    assert queued_site_ids(db) == {never_scanned.id, stale.id}
    queued = list(db.execute(select(Scan).where(Scan.status == ScanStatus.QUEUED)).scalars())
    assert {scan.trigger_type for scan in queued} == {ScanTriggerType.SCHEDULED}
    assert {scan.triggered_by_user_id for scan in queued} == {None}
    assert {call for call in task_calls} == {(EXECUTE, (str(scan.id),)) for scan in queued}


def test_the_hourly_check_does_not_queue_the_same_site_twice(db, dept, vendor_a):
    site = factories.make_site(db, dept, vendor=vendor_a)

    dispatch()
    dispatch()

    assert len(list(db.execute(select(Scan).where(Scan.site_id == site.id)).scalars())) == 1


def test_scheduled_scans_respect_the_authorization_rule(db, dept, admin, vendor_a, task_calls):
    blocked = factories.make_site(db, dept, vendor=vendor_a, name="Blocked", url="https://blocked.example.gov.in", is_gov_in=True)
    allowed = factories.make_site(db, dept, vendor=vendor_a, name="Allowed", url="https://allowed.example.gov.in", is_gov_in=True)
    db.add(
        AuthorizationRecord(
            site_id=allowed.id,
            document_reference="Letter 7/2026",
            granted_by_user_id=admin.id,
            granted_at=datetime.now(timezone.utc),
        )
    )
    db.flush()

    dispatch()

    assert queued_site_ids(db) == {allowed.id}
    assert blocked.id not in queued_site_ids(db)
    assert len(task_calls) == 1