"""Housekeeping tasks run by Celery Beat.

fail_stuck_scans: a worker that crashes mid-scan leaves its scan marked RUNNING
for good, and that blocks every later scan of the site. A scan that has been
RUNNING for over an hour, or QUEUED for over two (so its task was lost), is
marked failed and the admins are told. A failed verification scan leaves its
ticket as it was, and the admin can re-run verification from the ticket.
"""
from datetime import datetime, timedelta, timezone

from sqlalchemy import and_, func, or_, select

from app.database import SessionLocal
from app.models.enums import ScanStatus
from app.models.scan import Scan
from app.tasks.celery_app import celery_app
from app.tasks.notification_tasks import notify_scan_failed

RUNNING_STUCK_AFTER = timedelta(minutes=60)
QUEUED_STUCK_AFTER = timedelta(minutes=120)

RUNNING_REASON = "The worker stopped before this scan finished."
QUEUED_REASON = "This scan was never picked up by a worker."


@celery_app.task(name="app.tasks.maintenance_tasks.fail_stuck_scans")
def fail_stuck_scans() -> int:
    """Returns how many scans were marked failed."""
    db = SessionLocal()
    try:
        now = datetime.now(timezone.utc)
        began = func.coalesce(Scan.started_at, Scan.queued_at)
        stuck = db.execute(
            select(Scan).where(
                or_(
                    and_(Scan.status == ScanStatus.RUNNING, began < now - RUNNING_STUCK_AFTER),
                    and_(Scan.status == ScanStatus.QUEUED, Scan.queued_at < now - QUEUED_STUCK_AFTER),
                )
            )
        ).scalars().all()

        reports: list[tuple[str, str, str]] = []
        for scan in stuck:
            reason = RUNNING_REASON if scan.status == ScanStatus.RUNNING else QUEUED_REASON
            scan.status = ScanStatus.FAILED
            scan.error_message = reason
            scan.completed_at = now
            reports.append((str(scan.site_id), str(scan.id), reason))
        db.commit()

        for site_id, scan_id, reason in reports:
            notify_scan_failed.delay(site_id, scan_id, reason)
        return len(reports)
    finally:
        db.close()