"""The admin's "Re-run verification" call: when it is allowed and what it queues."""
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.models.audit_log import AuditLog
from app.models.enums import AuditAction, FindingStatus, ScanStatus, ScanTriggerType, TicketStatus
from tests import factories
from tests.factories import bearer
from tests.lifecycle.helpers import API

VERIFY_TASK = "app.tasks.verification_tasks.run_verification_scan"


@pytest.fixture()
def waiting(db, open_ticket):
    open_ticket.status = TicketStatus.FIX_SUBMITTED_PENDING_VERIFICATION
    db.flush()
    return open_ticket


def rescan(db, site, ticket, status, minutes_old=0):
    scan = factories.make_scan(db, site, status=status, trigger=ScanTriggerType.VERIFICATION)
    scan.verification_ticket_id = ticket.id
    scan.queued_at = datetime.now(timezone.utc) - timedelta(minutes=minutes_old)
    db.flush()
    return scan


def reverify(client, admin, ticket):
    return client.post(f"{API}/tickets/{ticket.id}/reverify", headers=bearer(admin))


def test_a_waiting_ticket_can_be_re_run_and_the_request_is_audited(client, db, admin, waiting, task_calls):
    response = reverify(client, admin, waiting)

    assert response.status_code == 200
    assert task_calls == [(VERIFY_TASK, (str(waiting.id),))]
    entry = db.execute(
        select(AuditLog).where(AuditLog.entity_id == waiting.id, AuditLog.action == AuditAction.SCAN_TRIGGERED)
    ).scalar_one()
    assert entry.actor_id == admin.id
    assert entry.metadata_json["reason"] == "manual re-verification"


@pytest.mark.parametrize("status", [ScanStatus.RUNNING, ScanStatus.QUEUED])
def test_a_live_re_scan_blocks_another_one(client, db, admin, site, waiting, task_calls, status):
    rescan(db, site, waiting, status)

    response = reverify(client, admin, waiting)

    assert response.status_code == 409
    assert "already running" in response.json()["error"]["message"]
    assert task_calls == []


def test_a_re_scan_that_has_been_stuck_for_a_long_time_does_not_block(client, db, admin, site, waiting, task_calls):
    rescan(db, site, waiting, ScanStatus.RUNNING, minutes_old=40)

    assert reverify(client, admin, waiting).status_code == 200
    assert len(task_calls) == 1


@pytest.mark.parametrize("status", [ScanStatus.FAILED, ScanStatus.COMPLETED])
def test_a_finished_re_scan_does_not_block(client, db, admin, site, waiting, task_calls, status):
    rescan(db, site, waiting, status)

    assert reverify(client, admin, waiting).status_code == 200
    assert len(task_calls) == 1


def test_another_tickets_re_scan_does_not_block(client, db, admin, site, vendor_a, waiting, task_calls):
    other_finding = factories.make_finding(db, site, status=FindingStatus.APPROVED, endpoint="/other")
    other = factories.make_ticket(db, other_finding, vendor_a, status=TicketStatus.FIX_SUBMITTED_PENDING_VERIFICATION)
    rescan(db, site, other, ScanStatus.RUNNING)

    assert reverify(client, admin, waiting).status_code == 200


@pytest.mark.parametrize("status", [TicketStatus.OPEN, TicketStatus.OVERDUE, TicketStatus.VERIFIED_CLOSED])
def test_only_a_ticket_waiting_for_a_re_scan_can_be_re_run(client, db, admin, open_ticket, task_calls, status):
    open_ticket.status = status
    db.flush()

    assert reverify(client, admin, open_ticket).status_code == 409
    assert task_calls == []


def test_another_departments_ticket_is_not_found(client, db, admin, task_calls):
    department = factories.make_department(db)
    vendor = factories.make_vendor(db, department)
    site = factories.make_site(db, department, vendor=vendor)
    finding = factories.make_finding(db, site, status=FindingStatus.APPROVED)
    foreign = factories.make_ticket(db, finding, vendor, status=TicketStatus.FIX_SUBMITTED_PENDING_VERIFICATION)

    assert reverify(client, admin, foreign).status_code == 404
    assert task_calls == []