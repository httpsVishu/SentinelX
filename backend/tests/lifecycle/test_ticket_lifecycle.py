"""Ticket assignment, deadline override, vendor remediation and overdue detection."""
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.models.audit_log import AuditLog
from app.models.enums import (
    AlertLevel,
    AlertDeliveryStatus,
    AlertTriggerType,
    AuditAction,
    DeadlineSource,
    FindingStatus,
    TicketStatus,
)
from app.models.ticket import RemediationSubmission
from tests import factories
from tests.factories import bearer, make_department, make_vendor
from tests.lifecycle.helpers import API, XSS_ENDPOINT, alerts_for, audit_actions, submit_fix

VERIFY_TASK = "app.tasks.verification_tasks.run_verification_scan"


def assign(client, admin, ticket, **body):
    return client.post(f"{API}/tickets/{ticket.id}/assign", headers=bearer(admin), json=body)


@pytest.fixture()
def unassigned_ticket(db, dept):
    site = factories.make_site(db, dept, vendor=None, name="No vendor site")
    finding = factories.make_finding(db, site, status=FindingStatus.APPROVED)
    return factories.make_ticket(db, finding, None)


def in_days(days):
    return datetime.now(timezone.utc) + timedelta(days=days)


# ---- Assignment ----

def test_assigning_a_vendor_opens_the_ticket(client, db, admin, vendor_a, unassigned_ticket):
    response = assign(client, admin, unassigned_ticket, vendor_id=str(vendor_a.id))

    assert response.status_code == 200
    db.refresh(unassigned_ticket)
    assert unassigned_ticket.status == TicketStatus.OPEN
    assert unassigned_ticket.vendor_id == vendor_a.id
    assert AuditAction.TICKET_VENDOR_ASSIGNED in audit_actions(db, unassigned_ticket.id)


def test_an_unassigned_ticket_cannot_be_confirmed_without_a_vendor(client, db, admin, unassigned_ticket):
    response = assign(client, admin, unassigned_ticket)

    assert response.status_code == 400
    db.refresh(unassigned_ticket)
    assert unassigned_ticket.status == TicketStatus.UNASSIGNED


def test_a_vendor_from_another_department_cannot_be_assigned(client, db, admin, unassigned_ticket):
    outsider = make_vendor(db, make_department(db))

    response = assign(client, admin, unassigned_ticket, vendor_id=str(outsider.id))

    assert response.status_code == 404
    db.refresh(unassigned_ticket)
    assert unassigned_ticket.vendor_id is None
    assert unassigned_ticket.status == TicketStatus.UNASSIGNED


@pytest.mark.parametrize(
    "status",
    [TicketStatus.OVERDUE, TicketStatus.FIX_SUBMITTED_PENDING_VERIFICATION, TicketStatus.VERIFIED_CLOSED],
)
def test_a_ticket_in_progress_cannot_be_reassigned(client, db, admin, vendor_a, vendor_b, site, status):
    finding = factories.make_finding(db, site, status=FindingStatus.APPROVED, endpoint="/in-progress")
    ticket = factories.make_ticket(db, finding, vendor_a, status=status)

    response = assign(client, admin, ticket, vendor_id=str(vendor_b.id))

    assert response.status_code == 409
    db.refresh(ticket)
    assert ticket.vendor_id == vendor_a.id


# ---- Deadline override ----

def test_overriding_a_deadline_keeps_the_original_and_records_why(client, db, admin, open_ticket):
    original = open_ticket.deadline
    new_deadline = in_days(20)

    response = assign(
        client, admin, open_ticket,
        deadline_override=new_deadline.isoformat(), override_reason="Vendor needs a release window.",
    )

    assert response.status_code == 200
    db.refresh(open_ticket)
    assert abs((open_ticket.deadline - new_deadline).total_seconds()) < 1
    assert open_ticket.deadline_source == DeadlineSource.OVERRIDE
    assert open_ticket.override_reason == "Vendor needs a release window."
    assert open_ticket.suggested_deadline == original  # the suggestion stays traceable

    entry = db.execute(
        select(AuditLog).where(
            AuditLog.entity_id == open_ticket.id, AuditLog.action == AuditAction.TICKET_DEADLINE_OVERRIDDEN
        )
    ).scalar_one()
    assert entry.actor_id == admin.id
    assert entry.metadata_json["reason"] == "Vendor needs a release window."


@pytest.mark.parametrize("reason", [None, "", "   "])
def test_an_override_needs_a_reason(client, db, admin, open_ticket, reason):
    original = open_ticket.deadline
    body = {"deadline_override": in_days(20).isoformat()}
    if reason is not None:
        body["override_reason"] = reason

    response = assign(client, admin, open_ticket, **body)

    assert response.status_code == 400
    db.refresh(open_ticket)
    assert open_ticket.deadline == original
    assert open_ticket.deadline_source == DeadlineSource.AUTO
    assert open_ticket.override_reason is None


def test_a_vendor_cannot_change_the_deadline(client, db, vendor_a_user, open_ticket):
    original = open_ticket.deadline

    response = client.post(
        f"{API}/tickets/mine/{open_ticket.id}/remediate",
        headers=bearer(vendor_a_user),
        json={"note": "Fixed.", "deadline": in_days(365).isoformat(), "deadline_override": in_days(365).isoformat()},
    )

    assert response.status_code == 200
    db.refresh(open_ticket)
    assert open_ticket.deadline == original


# ---- Database rules ----

def test_a_ticket_without_a_vendor_must_be_unassigned(db, open_ticket):
    open_ticket.vendor_id = None

    with pytest.raises(IntegrityError):
        db.flush()


# ---- Remediation ----

def test_reporting_a_fix_records_it_and_waits_for_a_re_scan(client, db, vendor_a_user, open_ticket, task_calls):
    response = submit_fix(client, vendor_a_user, open_ticket, note="Upgraded the library.")

    assert response.status_code == 200
    assert response.json()["status"] == "fix_submitted_pending_verification"

    db.refresh(open_ticket)
    assert open_ticket.status == TicketStatus.FIX_SUBMITTED_PENDING_VERIFICATION
    assert open_ticket.closed_at is None  # a claim alone never closes a ticket

    saved = db.execute(select(RemediationSubmission).where(RemediationSubmission.ticket_id == open_ticket.id)).scalar_one()
    assert saved.note == "Upgraded the library."
    assert saved.vendor_user_id == vendor_a_user.id
    assert AuditAction.REMEDIATION_SUBMITTED in audit_actions(db, open_ticket.id)
    assert task_calls == [(VERIFY_TASK, (str(open_ticket.id),))]


def test_a_fix_report_needs_a_note(client, vendor_a_user, open_ticket, task_calls):
    response = client.post(f"{API}/tickets/mine/{open_ticket.id}/remediate", headers=bearer(vendor_a_user), json={"note": ""})

    assert response.status_code == 422
    assert task_calls == []


@pytest.mark.parametrize("status", [TicketStatus.OPEN, TicketStatus.OVERDUE, TicketStatus.FIX_FAILED_REOPENED])
def test_a_fix_can_be_reported_while_the_ticket_is_unresolved(client, db, vendor_a, vendor_a_user, site, status):
    finding = factories.make_finding(db, site, status=FindingStatus.APPROVED, endpoint=f"/{status.value}")
    ticket = factories.make_ticket(db, finding, vendor_a, status=status)

    assert submit_fix(client, vendor_a_user, ticket).status_code == 200


@pytest.mark.parametrize("status", [TicketStatus.VERIFIED_CLOSED, TicketStatus.FIX_SUBMITTED_PENDING_VERIFICATION])
def test_a_fix_cannot_be_reported_twice_or_after_closing(client, db, vendor_a, vendor_a_user, site, status, task_calls):
    finding = factories.make_finding(db, site, status=FindingStatus.APPROVED, endpoint=f"/{status.value}")
    ticket = factories.make_ticket(db, finding, vendor_a, status=status)

    assert submit_fix(client, vendor_a_user, ticket).status_code == 409
    assert task_calls == []


# ---- Overdue detection ----

def run_deadline_check():
    from app.tasks.deadline_tasks import check_overdue_tickets

    check_overdue_tickets()


def test_the_daily_check_marks_overdue_tickets_and_alerts_admin_and_vendor(
    db, admin, vendor_a, vendor_a_user, site, xss_finding
):
    ticket = factories.make_ticket(db, xss_finding, vendor_a, deadline=in_days(-1))

    run_deadline_check()

    db.refresh(ticket)
    assert ticket.status == TicketStatus.OVERDUE

    for recipient in (admin, vendor_a_user):
        alerts = alerts_for(db, recipient, AlertTriggerType.DEADLINE_MISSED)
        assert len(alerts) == 1
        assert alerts[0].level == AlertLevel.URGENT
        assert alerts[0].ticket_id == ticket.id
        assert alerts[0].delivery_status == AlertDeliveryStatus.DELIVERED
        assert site.name in alerts[0].message
        assert XSS_ENDPOINT not in alerts[0].message  # no finding detail in a notification


def test_running_the_check_again_does_not_alert_again(db, admin, vendor_a, xss_finding):
    factories.make_ticket(db, xss_finding, vendor_a, deadline=in_days(-1))

    run_deadline_check()
    run_deadline_check()

    assert len(alerts_for(db, admin, AlertTriggerType.DEADLINE_MISSED)) == 1


def test_the_check_only_touches_open_tickets_past_their_deadline(db, dept, vendor_a, site):
    def ticket_with(status, days, endpoint):
        finding = factories.make_finding(db, site, status=FindingStatus.APPROVED, endpoint=endpoint)
        return factories.make_ticket(db, finding, vendor_a, status=status, deadline=in_days(days))

    due = ticket_with(TicketStatus.OPEN, -2, "/due")
    not_due = ticket_with(TicketStatus.OPEN, 2, "/not-due")
    waiting = ticket_with(TicketStatus.FIX_SUBMITTED_PENDING_VERIFICATION, -2, "/waiting")
    closed = ticket_with(TicketStatus.VERIFIED_CLOSED, -2, "/closed")

    run_deadline_check()

    for ticket in (due, not_due, waiting, closed):
        db.refresh(ticket)
    assert due.status == TicketStatus.OVERDUE
    assert not_due.status == TicketStatus.OPEN
    assert waiting.status == TicketStatus.FIX_SUBMITTED_PENDING_VERIFICATION
    assert closed.status == TicketStatus.VERIFIED_CLOSED