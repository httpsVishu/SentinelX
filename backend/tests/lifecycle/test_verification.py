"""Fix verification: pass, fail, scanner outage, and the rules that stop a
ticket from being closed without a real re-scan."""
import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError

from app.agents import assessment_agent
from app.config import settings
from app.models.agent_execution import AgentExecution
from app.models.enums import (
    AgentName,
    AlertLevel,
    AlertTriggerType,
    AuditAction,
    FindingStatus,
    ScanStatus,
    ScanTriggerType,
    TicketStatus,
    VerificationResult,
)
from app.models.scan import Scan
from app.models.ticket import VerificationRecord
from app.scanners import get_scanner_adapters
from app.scanners.base import ScannerAdapter, ScannerError
from app.services.ticket_service import InvalidTicketTransition, record_verification_result
from tests import factories
from tests.factories import POC_TEXT, bearer
from tests.lifecycle.helpers import API, XSS_ENDPOINT, alerts_for, audit_actions, submit_fix

VERIFY_TASK = "app.tasks.verification_tasks.run_verification_scan"


class BrokenScanner(ScannerAdapter):
    name = "broken"

    def scan(self, target_url, excluded_paths, scope_paths=None):
        raise ScannerError("scanner is down")


def verify(ticket):
    from app.tasks.verification_tasks import run_verification_scan

    run_verification_scan(str(ticket.id))


def records_for(db, ticket):
    return list(db.execute(select(VerificationRecord).where(VerificationRecord.ticket_id == ticket.id)).scalars())


def commit_checks_pass(db):
    # The ticket-closure rule is checked when a transaction commits. Tests never
    # commit, so run the pending checks now.
    db.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))


# ---- A fix that works ----

def test_a_fix_that_passes_the_re_scan_closes_the_ticket(client, db, admin, vendor_a_user, open_ticket):
    assert submit_fix(client, vendor_a_user, open_ticket).status_code == 200
    db.refresh(open_ticket)
    assert open_ticket.status == TicketStatus.FIX_SUBMITTED_PENDING_VERIFICATION

    verify(open_ticket)

    db.refresh(open_ticket)
    assert open_ticket.status == TicketStatus.VERIFIED_CLOSED
    assert open_ticket.closed_at is not None

    record = records_for(db, open_ticket)[0]
    assert record.result == VerificationResult.PASSED
    scan = db.get(Scan, record.scan_id)
    assert scan.trigger_type == ScanTriggerType.VERIFICATION
    assert scan.status == ScanStatus.COMPLETED
    assert scan.target_scope == [XSS_ENDPOINT]  # only the affected endpoint was re-scanned
    assert scan.verification_ticket_id == open_ticket.id

    agents = {e.agent_name for e in db.execute(select(AgentExecution).where(AgentExecution.scan_id == scan.id)).scalars()}
    assert agents == {AgentName.ASSESSMENT, AgentName.VALIDATION, AgentName.VERIFICATION}

    actions = audit_actions(db, open_ticket.id)
    assert AuditAction.VERIFICATION_PASSED in actions
    assert AuditAction.TICKET_CLOSED in actions
    assert alerts_for(db, admin, AlertTriggerType.VERIFICATION_FAILED) == []
    commit_checks_pass(db)


# ---- A fix that does not work ----

def test_a_failed_re_scan_reopens_the_ticket_alerts_both_sides_and_allows_another_try(
    client, db, admin, vendor_a_user, open_ticket, monkeypatch
):
    monkeypatch.setattr(settings, "MOCK_FIXES_REQUIRED", 2)  # the first fix does not hold

    submit_fix(client, vendor_a_user, open_ticket, note="First attempt.")
    verify(open_ticket)

    db.refresh(open_ticket)
    assert open_ticket.status == TicketStatus.FIX_FAILED_REOPENED
    assert open_ticket.closed_at is None
    assert [r.result for r in records_for(db, open_ticket)] == [VerificationResult.FAILED]
    assert AuditAction.VERIFICATION_FAILED in audit_actions(db, open_ticket.id)
    assert AuditAction.TICKET_CLOSED not in audit_actions(db, open_ticket.id)

    for recipient in (admin, vendor_a_user):
        alerts = alerts_for(db, recipient, AlertTriggerType.VERIFICATION_FAILED)
        assert len(alerts) == 1
        assert alerts[0].level == AlertLevel.URGENT
        assert POC_TEXT not in alerts[0].message

    # The vendor tries again, and this time the issue is gone.
    assert submit_fix(client, vendor_a_user, open_ticket, note="Second attempt.").status_code == 200
    verify(open_ticket)

    db.refresh(open_ticket)
    assert open_ticket.status == TicketStatus.VERIFIED_CLOSED
    assert {r.result for r in records_for(db, open_ticket)} == {VerificationResult.FAILED, VerificationResult.PASSED}
    commit_checks_pass(db)


def test_a_different_issue_on_the_same_endpoint_does_not_fail_a_good_fix(
    client, db, vendor_a, vendor_a_user, site, monkeypatch
):
    monkeypatch.setattr(settings, "MOCK_FIXES_REQUIRED", 2)  # the scanner still reports the XSS finding
    finding = factories.make_finding(
        db, site, status=FindingStatus.APPROVED, endpoint=XSS_ENDPOINT, title="Some other issue that was fixed"
    )
    ticket = factories.make_ticket(db, finding, vendor_a)

    submit_fix(client, vendor_a_user, ticket)
    verify(ticket)

    db.refresh(ticket)
    assert ticket.status == TicketStatus.VERIFIED_CLOSED


# ---- A scanner outage ----

def test_a_scanner_outage_never_closes_a_ticket_and_the_admin_can_run_it_again(
    client, db, admin, vendor_a_user, open_ticket, monkeypatch, task_calls
):
    monkeypatch.setattr(assessment_agent, "get_scanner_adapters", lambda: [BrokenScanner()])

    submit_fix(client, vendor_a_user, open_ticket)
    verify(open_ticket)

    db.refresh(open_ticket)
    assert open_ticket.status == TicketStatus.FIX_SUBMITTED_PENDING_VERIFICATION  # not closed, not reopened
    assert records_for(db, open_ticket) == []

    scan = db.execute(select(Scan).where(Scan.verification_ticket_id == open_ticket.id)).scalar_one()
    assert scan.status == ScanStatus.FAILED
    assert "scanner is down" in scan.error_message

    alerts = alerts_for(db, admin, AlertTriggerType.SCAN_FAILED)
    assert len(alerts) == 1
    assert alerts[0].ticket_id == open_ticket.id
    commit_checks_pass(db)

    # The scanner is back. The admin asks for another check.
    monkeypatch.setattr(assessment_agent, "get_scanner_adapters", get_scanner_adapters)
    response = client.post(f"{API}/tickets/{open_ticket.id}/reverify", headers=bearer(admin))
    assert response.status_code == 200
    assert task_calls[-1] == (VERIFY_TASK, (str(open_ticket.id),))

    verify(open_ticket)

    db.refresh(open_ticket)
    assert open_ticket.status == TicketStatus.VERIFIED_CLOSED
    commit_checks_pass(db)


def test_only_a_ticket_waiting_for_a_re_scan_can_be_re_verified(client, admin, vendor_a_user, open_ticket, task_calls):
    assert client.post(f"{API}/tickets/{open_ticket.id}/reverify", headers=bearer(admin)).status_code == 409
    assert client.post(f"{API}/tickets/{open_ticket.id}/reverify", headers=bearer(vendor_a_user)).status_code == 403
    assert task_calls == []


# ---- Rules that stop an early close ----

def test_the_verification_task_ignores_a_ticket_nobody_claimed_a_fix_for(db, open_ticket):
    verify(open_ticket)

    db.refresh(open_ticket)
    assert open_ticket.status == TicketStatus.OPEN
    assert db.execute(select(Scan).where(Scan.verification_ticket_id == open_ticket.id)).first() is None


def test_a_ticket_without_a_submitted_fix_cannot_be_closed_by_the_service(db, site, open_ticket):
    scan = factories.make_scan(db, site, trigger=ScanTriggerType.VERIFICATION)

    with pytest.raises(InvalidTicketTransition):
        record_verification_result(db, open_ticket.id, scan.id, VerificationResult.PASSED)

    db.refresh(open_ticket)
    assert open_ticket.status == TicketStatus.OPEN
    assert records_for(db, open_ticket) == []


def test_the_database_refuses_to_close_a_ticket_without_a_passed_re_scan(db, open_ticket):
    open_ticket.status = TicketStatus.VERIFIED_CLOSED
    db.flush()

    with pytest.raises(IntegrityError):
        commit_checks_pass(db)


def test_the_database_accepts_a_close_that_has_a_passed_re_scan(db, site, open_ticket):
    scan = factories.make_scan(db, site, trigger=ScanTriggerType.VERIFICATION)
    db.add(VerificationRecord(ticket_id=open_ticket.id, scan_id=scan.id, result=VerificationResult.PASSED))
    open_ticket.status = TicketStatus.VERIFIED_CLOSED
    db.flush()

    commit_checks_pass(db)