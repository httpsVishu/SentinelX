"""The scan pipeline: findings, safety verdicts, deduplication, alerts, and the
scan task around it. Reconnaissance is stubbed so no test touches the network."""
import pytest
from sqlalchemy import select

from app.agents.base_agent import REDACTED_RAW_OUTPUT
from app.core.crypto import decrypt_text
from app.models.agent_execution import AgentExecution
from app.models.enums import (
    AgentExecutionStatus,
    AgentName,
    AlertLevel,
    AlertTriggerType,
    FindingStatus,
    ScanStatus,
    ScanTriggerType,
    TicketStatus,
)
from app.models.finding import Finding
from app.models.ticket import Ticket
from app.orchestration.graph import run_scan_pipeline
from tests import factories
from tests.lifecycle.helpers import XSS_ENDPOINT, XSS_TITLE, alerts_for

HEADERS_TITLE = "Missing security headers"
LIBRARY_TITLE = "Outdated client-side JavaScript library with known CVEs"
SQLI_TITLE = "SQL Injection in login form"
COMMAND_TITLE = "Command Injection in ping utility"
COOKIE_TITLE = "Weak session cookie attributes"


@pytest.fixture(autouse=True)
def offline_recon(monkeypatch):
    from app.agents.recon_agent import ReconAgent

    monkeypatch.setattr(
        ReconAgent,
        "_fetch_headers_and_links",
        lambda self, url, excluded: {"headers_by_path": {"/": {"Server": "nginx"}}, "reachable_paths": ["/", "/api"]},
    )


def scan_once(db, site):
    scan = factories.make_scan(db, site, status=ScanStatus.RUNNING, trigger=ScanTriggerType.MANUAL)
    run_scan_pipeline(db, scan.id, site)
    return scan


def findings_of(db, site):
    return list(db.execute(select(Finding).where(Finding.site_id == site.id)).scalars())


@pytest.fixture()
def dvwa(db, dept, vendor_b):
    return factories.make_site(db, dept, vendor=vendor_b, name="DVWA", url="http://dvwa.local:8080")


# ---- What a scan produces ----

def test_a_scan_stores_confirmed_findings_for_review_with_encrypted_proof(db, site):
    scan_once(db, site)

    by_title = {f.title: f for f in findings_of(db, site)}
    assert {t: f.status for t, f in by_title.items()} == {
        XSS_TITLE: FindingStatus.PENDING_ADMIN_REVIEW,
        HEADERS_TITLE: FindingStatus.PENDING_ADMIN_REVIEW,
        LIBRARY_TITLE: FindingStatus.PENDING_ADMIN_REVIEW,
    }
    xss = by_title[XSS_TITLE]
    assert "read-only" in decrypt_text(db, xss.poc_summary_encrypted)
    assert db.execute(select(Ticket)).first() is None  # nothing becomes a ticket without Admin approval


def test_every_stage_of_the_scan_is_recorded_and_raw_output_is_not_kept_in_plaintext(db, site):
    scan = scan_once(db, site)

    executions = list(db.execute(select(AgentExecution).where(AgentExecution.scan_id == scan.id)).scalars())
    assert {e.agent_name for e in executions} == {
        AgentName.RECON, AgentName.MAPPING, AgentName.ASSESSMENT, AgentName.VALIDATION,
    }
    assert {e.status for e in executions} == {AgentExecutionStatus.SUCCEEDED}

    assessment = next(e for e in executions if e.agent_name == AgentName.ASSESSMENT)
    raw_findings = assessment.output_snapshot["raw_findings"]
    assert raw_findings
    assert all(f["raw_output"] == REDACTED_RAW_OUTPUT for f in raw_findings)


def test_excluded_paths_are_left_out(db, dept, vendor_a):
    site = factories.make_site(
        db, dept, vendor=vendor_a, url="http://juice-shop.local:3000", excluded_paths=["/rest"]
    )

    scan_once(db, site)

    titles = {f.title for f in findings_of(db, site)}
    assert XSS_TITLE not in titles  # that endpoint is under /rest
    assert HEADERS_TITLE in titles


# ---- Safety ----

def test_a_finding_that_would_need_a_risky_check_goes_to_a_human_not_the_queue(db, dvwa):
    scan_once(db, dvwa)

    by_title = {f.title: f for f in findings_of(db, dvwa)}
    command = by_title[COMMAND_TITLE]
    assert command.status == FindingStatus.NEEDS_MANUAL_REVIEW
    assert command.poc_summary_encrypted is None  # nothing was run to prove it
    assert by_title[SQLI_TITLE].status == FindingStatus.PENDING_ADMIN_REVIEW


# ---- Alerts ----

def test_a_high_finding_alerts_the_admin_without_exploit_detail(db, admin, site):
    scan_once(db, site)

    xss = next(f for f in findings_of(db, site) if f.title == XSS_TITLE)
    alerts = alerts_for(db, admin, AlertTriggerType.HIGH_FINDING_CONFIRMED)
    assert len(alerts) == 1
    assert alerts[0].finding_id == xss.id
    assert alerts[0].level == AlertLevel.WARNING
    assert XSS_ENDPOINT not in alerts[0].message
    assert alerts_for(db, admin, AlertTriggerType.CRITICAL_FINDING_CONFIRMED) == []


def test_a_critical_finding_raises_an_urgent_alert(db, admin, dvwa):
    scan_once(db, dvwa)

    alerts = alerts_for(db, admin, AlertTriggerType.CRITICAL_FINDING_CONFIRMED)
    assert len(alerts) == 1
    assert alerts[0].level == AlertLevel.URGENT
    sqli = next(f for f in findings_of(db, dvwa) if f.title == SQLI_TITLE)
    assert alerts[0].finding_id == sqli.id


# ---- Repeat scans ----

def test_scanning_again_does_not_duplicate_findings(db, site):
    scan_once(db, site)
    scan_once(db, site)

    assert len(findings_of(db, site)) == 3


def test_a_rejected_finding_is_not_raised_again(db, site):
    scan_once(db, site)
    xss = next(f for f in findings_of(db, site) if f.title == XSS_TITLE)
    xss.status = FindingStatus.REJECTED
    db.flush()

    scan_once(db, site)

    assert len(findings_of(db, site)) == 3
    db.refresh(xss)
    assert xss.status == FindingStatus.REJECTED


def test_an_issue_that_returns_after_a_verified_fix_is_a_new_finding(db, site, vendor_a):
    scan_once(db, site)
    xss = next(f for f in findings_of(db, site) if f.title == XSS_TITLE)
    xss.status = FindingStatus.APPROVED
    factories.make_ticket(db, xss, vendor_a, status=TicketStatus.VERIFIED_CLOSED)
    db.flush()

    scan_once(db, site)

    xss_findings = [f for f in findings_of(db, site) if f.title == XSS_TITLE]
    assert len(xss_findings) == 2
    assert {f.status for f in xss_findings} == {FindingStatus.APPROVED, FindingStatus.PENDING_ADMIN_REVIEW}


# ---- The scan task ----

def test_the_scan_task_marks_the_scan_and_the_site(db, site):
    from app.tasks.scan_tasks import execute_scan

    scan = factories.make_scan(db, site, status=ScanStatus.QUEUED, trigger=ScanTriggerType.MANUAL)

    execute_scan(str(scan.id))

    db.refresh(scan)
    db.refresh(site)
    assert scan.status == ScanStatus.COMPLETED
    assert scan.started_at is not None
    assert scan.completed_at is not None
    assert site.last_scanned_at is not None


def test_a_failed_scan_is_marked_failed_and_reported(db, site, monkeypatch, task_calls):
    from app.tasks.scan_tasks import execute_scan

    def boom(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr("app.tasks.scan_tasks.run_scan_pipeline", boom)
    scan = factories.make_scan(db, site, status=ScanStatus.QUEUED, trigger=ScanTriggerType.MANUAL)

    execute_scan(str(scan.id))

    db.refresh(scan)
    assert scan.status == ScanStatus.FAILED
    assert scan.error_message == "boom"
    assert task_calls == [("app.tasks.notification_tasks.notify_scan_failed", (str(site.id), str(scan.id), "boom"))]


def test_the_failure_alert_tells_the_admin_which_scan_without_the_error_text(db, admin, site):
    from app.tasks.notification_tasks import notify_scan_failed

    scan = factories.make_scan(db, site, status=ScanStatus.FAILED)

    notify_scan_failed(str(site.id), str(scan.id), "boom")

    alerts = alerts_for(db, admin, AlertTriggerType.SCAN_FAILED)
    assert len(alerts) == 1
    assert str(scan.id) in alerts[0].message
    assert "boom" not in alerts[0].message
