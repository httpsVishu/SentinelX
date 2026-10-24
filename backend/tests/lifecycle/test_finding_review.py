"""The Admin review workflow and the approval task that follows it."""
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.core.crypto import decrypt_text
from app.models.agent_execution import AgentExecution
from app.models.audit_log import AuditLog
from app.models.enums import (
    AgentName,
    AlertTriggerType,
    AuditAction,
    DeadlineSource,
    FindingStatus,
    ReviewDecision,
    Severity,
    TicketStatus,
)
from app.models.finding import Finding, FindingReview
from app.models.ticket import Ticket
from tests import factories
from tests.factories import POC_TEXT, RAW_OUTPUT_TEXT, bearer
from tests.lifecycle.helpers import API, alerts_for, audit_actions


def review(client, admin, finding, **body):
    return client.post(f"{API}/findings/{finding.id}/review", headers=bearer(admin), json=body)


def tickets_for(db, finding):
    return db.execute(select(Ticket).where(Ticket.finding_id == finding.id)).scalars().all()


@pytest.fixture()
def pending(db, site):
    return factories.make_finding(db, site, severity=Severity.HIGH, status=FindingStatus.PENDING_ADMIN_REVIEW)


# ---- The review queue ----

def test_queue_lists_only_findings_waiting_for_review_most_severe_first(client, db, admin, site):
    high = factories.make_finding(db, site, severity=Severity.HIGH, endpoint="/a")
    critical = factories.make_finding(db, site, severity=Severity.CRITICAL, endpoint="/b")
    factories.make_finding(db, site, status=FindingStatus.APPROVED, endpoint="/c")
    factories.make_finding(db, site, status=FindingStatus.DISCARDED, endpoint="/d")

    response = client.get(f"{API}/findings/pending-review", headers=bearer(admin))

    assert response.status_code == 200
    assert [item["id"] for item in response.json()] == [str(critical.id), str(high.id)]


def test_admin_sees_the_proof_summary_but_it_is_encrypted_at_rest(client, db, admin, pending):
    shown = client.get(f"{API}/findings/{pending.id}", headers=bearer(admin))
    assert shown.json()["poc_summary"] == POC_TEXT

    stored_proof = bytes(pending.poc_summary_encrypted)
    stored_raw = bytes(pending.raw_scanner_output_encrypted)
    assert POC_TEXT.encode() not in stored_proof
    assert RAW_OUTPUT_TEXT.encode() not in stored_raw
    assert decrypt_text(db, pending.poc_summary_encrypted) == POC_TEXT


# ---- Approve ----

def test_approving_records_the_review_and_queues_the_ticket_work(client, db, dept, admin, pending, approval_calls):
    response = review(client, admin, pending, decision="approve")

    assert response.status_code == 200
    assert response.json()["status"] == "approved"

    reviews = db.execute(select(FindingReview).where(FindingReview.finding_id == pending.id)).scalars().all()
    assert len(reviews) == 1
    assert reviews[0].reviewer_id == admin.id
    assert reviews[0].decision == ReviewDecision.APPROVE
    assert reviews[0].decided_at is not None
    assert AuditAction.FINDING_APPROVED in audit_actions(db, pending.id)

    assert approval_calls == [(str(pending.id), str(dept.id))]
    assert tickets_for(db, pending) == []  # the ticket comes from the task, not from the click


def test_a_finding_cannot_be_reviewed_twice(client, db, admin, pending, approval_calls):
    assert review(client, admin, pending, decision="approve").status_code == 200
    assert review(client, admin, pending, decision="reject", reason="Changed my mind.").status_code == 409

    db.refresh(pending)
    assert pending.status == FindingStatus.APPROVED
    assert len(approval_calls) == 1


@pytest.mark.parametrize("status", [FindingStatus.DISCARDED, FindingStatus.APPROVED, FindingStatus.NEEDS_MANUAL_REVIEW])
def test_only_findings_waiting_for_review_can_be_reviewed(client, db, admin, site, status, approval_calls):
    finding = factories.make_finding(db, site, status=status)

    assert review(client, admin, finding, decision="approve").status_code == 409
    assert approval_calls == []


# ---- Reject ----

@pytest.mark.parametrize("reason", [None, "", "   "])
def test_rejecting_needs_a_real_reason(client, db, admin, pending, approval_calls, reason):
    body = {"decision": "reject"}
    if reason is not None:
        body["reason"] = reason

    response = review(client, admin, pending, **body)

    assert response.status_code == 400
    db.refresh(pending)
    assert pending.status == FindingStatus.PENDING_ADMIN_REVIEW
    assert db.execute(select(FindingReview).where(FindingReview.finding_id == pending.id)).first() is None
    assert approval_calls == []


def test_rejecting_stores_who_why_and_when_and_makes_no_ticket(client, db, admin, pending, approval_calls):
    response = review(client, admin, pending, decision="reject", reason="  Test page, not exploitable.  ")

    assert response.status_code == 200
    assert response.json()["status"] == "rejected"

    saved = db.execute(select(FindingReview).where(FindingReview.finding_id == pending.id)).scalar_one()
    assert saved.reviewer_id == admin.id
    assert saved.reason == "Test page, not exploitable."
    assert saved.decided_at is not None

    entry = db.execute(
        select(AuditLog).where(AuditLog.entity_id == pending.id, AuditLog.action == AuditAction.FINDING_REJECTED)
    ).scalar_one()
    assert entry.metadata_json["reason"] == "Test page, not exploitable."
    assert tickets_for(db, pending) == []
    assert approval_calls == []


# ---- Database rule ----

def test_a_finding_cannot_be_confirmed_without_a_validation_record(db, site):
    scan = factories.make_scan(db, site)
    finding = Finding(
        site_id=site.id, scan_id=scan.id, title="Unvalidated", description="x", severity=Severity.HIGH,
        confidence=0.5, affected_endpoint="/x", status=FindingStatus.PENDING_ADMIN_REVIEW, validated_at=None,
    )
    db.add(finding)

    with pytest.raises(IntegrityError):
        db.flush()


# ---- The approval task ----

def run_approval(finding, dept):
    from app.tasks.approval_tasks import run_post_approval

    run_post_approval(str(finding.id), str(dept.id))


def test_approval_task_writes_the_report_and_opens_a_ticket(db, dept, vendor_a, xss_finding):
    run_approval(xss_finding, dept)

    ticket = db.execute(select(Ticket).where(Ticket.finding_id == xss_finding.id)).scalar_one()
    assert ticket.status == TicketStatus.OPEN
    assert ticket.vendor_id == vendor_a.id
    assert ticket.severity == Severity.HIGH
    assert ticket.deadline_source == DeadlineSource.AUTO
    assert ticket.deadline == ticket.suggested_deadline
    expected = datetime.now(timezone.utc) + timedelta(days=7)
    assert abs((ticket.deadline - expected).total_seconds()) < 120

    db.refresh(xss_finding)
    assert xss_finding.plain_language_report
    assert xss_finding.remediation_guidance

    agents = {
        e.agent_name
        for e in db.execute(select(AgentExecution).where(AgentExecution.scan_id == xss_finding.scan_id)).scalars()
    }
    assert {AgentName.REPORTING, AgentName.ACCOUNTABILITY} <= agents
    assert AuditAction.TICKET_CREATED in audit_actions(db, ticket.id)


def test_a_site_without_a_vendor_gets_an_unassigned_ticket(db, dept):
    site = factories.make_site(db, dept, vendor=None)
    finding = factories.make_finding(db, site, status=FindingStatus.APPROVED)

    run_approval(finding, dept)

    ticket = db.execute(select(Ticket).where(Ticket.finding_id == finding.id)).scalar_one()
    assert ticket.status == TicketStatus.UNASSIGNED
    assert ticket.vendor_id is None


def test_running_the_approval_task_twice_makes_one_ticket(db, dept, xss_finding):
    run_approval(xss_finding, dept)
    run_approval(xss_finding, dept)

    assert len(tickets_for(db, xss_finding)) == 1


def test_the_approval_task_ignores_a_finding_that_is_not_approved(db, dept, pending):
    run_approval(pending, dept)

    assert tickets_for(db, pending) == []


def test_admins_are_alerted_when_an_approved_finding_cannot_get_a_ticket(db, dept, admin, xss_finding, monkeypatch):
    from app.tasks import approval_tasks

    def broken_pipeline(*args, **kwargs):
        raise RuntimeError("model server is down")

    monkeypatch.setattr(approval_tasks, "run_post_approval_pipeline", broken_pipeline)
    monkeypatch.setattr(approval_tasks.run_post_approval, "max_retries", 0)  # skip straight to the final failure

    run_approval(xss_finding, dept)

    alerts = alerts_for(db, admin, AlertTriggerType.PIPELINE_FAILURE)
    assert len(alerts) == 1
    assert alerts[0].finding_id == xss_finding.id
    assert "model server is down" not in alerts[0].message
    assert tickets_for(db, xss_finding) == []