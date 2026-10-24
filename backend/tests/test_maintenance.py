"""Cleanup of scans that a crashed worker left behind."""
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.orm import sessionmaker

from app.models.enums import ScanStatus, ScanTriggerType
from app.tasks.maintenance_tasks import QUEUED_REASON, RUNNING_REASON, fail_stuck_scans
from tests import factories

NOTIFY = "app.tasks.notification_tasks.notify_scan_failed"


def minutes_ago(minutes):
    return datetime.now(timezone.utc) - timedelta(minutes=minutes)


@pytest.fixture(autouse=True)
def task_session(db, monkeypatch):
    """The task opens its own session. Point it at the test connection."""
    factory = sessionmaker(bind=db.get_bind(), autoflush=False, join_transaction_mode="create_savepoint")
    monkeypatch.setattr("app.tasks.maintenance_tasks.SessionLocal", factory)


@pytest.fixture()
def site(db, dept, vendor_a):
    return factories.make_site(db, dept, vendor=vendor_a)


def make(db, site, status, started=None, queued=None):
    scan = factories.make_scan(db, site, status=status, trigger=ScanTriggerType.SCHEDULED)
    scan.started_at = started
    scan.queued_at = queued or minutes_ago(1)
    db.flush()
    return scan


def test_a_scan_running_for_too_long_is_failed_and_the_admins_are_told(db, site, task_calls):
    scan = make(db, site, ScanStatus.RUNNING, started=minutes_ago(90), queued=minutes_ago(95))

    assert fail_stuck_scans() == 1

    db.refresh(scan)
    assert scan.status == ScanStatus.FAILED
    assert scan.error_message == RUNNING_REASON
    assert scan.completed_at is not None
    assert task_calls == [(NOTIFY, (str(site.id), str(scan.id), RUNNING_REASON))]


def test_a_scan_queued_for_too_long_is_failed(db, site, task_calls):
    scan = make(db, site, ScanStatus.QUEUED, queued=minutes_ago(180))

    assert fail_stuck_scans() == 1

    db.refresh(scan)
    assert scan.status == ScanStatus.FAILED
    assert scan.error_message == QUEUED_REASON
    assert task_calls == [(NOTIFY, (str(site.id), str(scan.id), QUEUED_REASON))]


def test_a_running_scan_with_no_start_time_is_judged_by_when_it_was_queued(db, site):
    scan = make(db, site, ScanStatus.RUNNING, started=None, queued=minutes_ago(90))

    assert fail_stuck_scans() == 1

    db.refresh(scan)
    assert scan.status == ScanStatus.FAILED


@pytest.mark.parametrize(
    "status,started,queued",
    [
        (ScanStatus.RUNNING, 30, 35),   # still within an hour
        (ScanStatus.QUEUED, None, 60),  # still within two hours
        (ScanStatus.COMPLETED, 500, 505),
        (ScanStatus.FAILED, 500, 505),
    ],
    ids=["recent running", "recent queued", "completed", "failed"],
)
def test_scans_that_are_not_stuck_are_left_alone(db, site, task_calls, status, started, queued):
    scan = make(
        db, site, status,
        started=minutes_ago(started) if started else None,
        queued=minutes_ago(queued),
    )

    assert fail_stuck_scans() == 0

    db.refresh(scan)
    assert scan.status == status
    assert task_calls == []


def test_the_site_can_be_scanned_again_once_the_stuck_scan_is_cleared(db, site):
    from app.services import scan_service

    stuck = make(db, site, ScanStatus.RUNNING, started=minutes_ago(90))
    assert scan_service.site_has_scan_in_flight(db, site.id)

    fail_stuck_scans()

    db.refresh(stuck)
    assert not scan_service.site_has_scan_in_flight(db, site.id)


def test_running_it_twice_reports_each_scan_once(db, site, task_calls):
    make(db, site, ScanStatus.RUNNING, started=minutes_ago(90))

    assert fail_stuck_scans() == 1
    assert fail_stuck_scans() == 0
    assert len(task_calls) == 1