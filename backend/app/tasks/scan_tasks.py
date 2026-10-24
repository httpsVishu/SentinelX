"""Celery tasks that start and run scans.

dispatch_due_scheduled_scans runs hourly (Celery Beat). For every active site
whose last scan is older than its frequency, it asks scan_service.trigger_scan
for a scheduled scan. That is the same entry point the Admin's "Scan now" uses,
so the authorization rule for restricted domains applies to scheduled scans too.

execute_scan runs the scan graph for one Scan row, with these rules:
  - Only a QUEUED scan runs. A redelivered task finds it handled and stops.
  - A restricted site with no stored authorization is never scanned, even if
    the Scan row was created some other way.
  - One scan per site at a time. A scan that finds another one running waits
    and retries every WAIT_SECONDS, for up to 30 minutes. After that it is
    marked failed and the admins are told, so it never sits queued unseen.
"""
import logging
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException
from sqlalchemy import select

from app.database import SessionLocal
from app.models.enums import ScanStatus, ScanTriggerType
from app.models.scan import Scan
from app.models.site import Site
from app.orchestration.graph import run_scan_pipeline
from app.services import scan_service
from app.services.authorization_service import ScanNotAuthorizedError, assert_scan_is_authorized
from app.services.scan_lock_service import release_site_scan_lock, try_acquire_site_scan_lock
from app.tasks.celery_app import celery_app
from app.tasks.notification_tasks import notify_scan_failed

logger = logging.getLogger("sentinelx.tasks.scan")

WAIT_SECONDS = 30
MAX_WAIT_RETRIES = 60  # 60 x 30 seconds = 30 minutes


@celery_app.task(name="app.tasks.scan_tasks.dispatch_due_scheduled_scans")
def dispatch_due_scheduled_scans() -> None:
    db = SessionLocal()
    try:
        now = datetime.now(timezone.utc)
        sites = db.execute(select(Site).where(Site.is_active.is_(True))).scalars().all()

        for site in sites:
            due = site.last_scanned_at is None or site.last_scanned_at <= now - timedelta(days=site.scan_frequency_days)
            if not due:
                continue
            if scan_service.site_has_scan_in_flight(db, site.id):
                continue  # the next hourly check tries again

            try:
                scan = scan_service.trigger_scan(db, site, ScanTriggerType.SCHEDULED)
            except HTTPException as exc:
                # Not authorized to scan, or paused. Nothing to run.
                logger.info("Scheduled scan of site %s skipped: %s", site.id, exc.detail)
                continue

            execute_scan.delay(str(scan.id))
    finally:
        db.close()


def _mark_failed(db, scan: Scan, site: Site, reason: str) -> None:
    scan.status = ScanStatus.FAILED
    scan.error_message = reason
    scan.completed_at = datetime.now(timezone.utc)
    db.commit()
    notify_scan_failed.delay(str(site.id), str(scan.id), reason)


@celery_app.task(
    name="app.tasks.scan_tasks.execute_scan",
    bind=True,
    max_retries=MAX_WAIT_RETRIES,
    default_retry_delay=WAIT_SECONDS,
)
def execute_scan(self, scan_id_str: str) -> None:
    scan_id = uuid.UUID(scan_id_str)
    db = SessionLocal()
    site: Site | None = None
    lock_acquired = False
    try:
        scan = db.execute(select(Scan).where(Scan.id == scan_id)).scalar_one_or_none()
        if scan is None or scan.status != ScanStatus.QUEUED:
            return  # already handled

        site = db.execute(select(Site).where(Site.id == scan.site_id)).scalar_one()

        try:
            assert_scan_is_authorized(db, site)
        except ScanNotAuthorizedError as exc:
            _mark_failed(db, scan, site, str(exc))
            return

        # This protects the check below from the time-of-check/time-of-use
        # race between two workers that receive queued scans together.
        if not try_acquire_site_scan_lock(db, site.id):
            if self.request.retries >= self.max_retries:
                _mark_failed(db, scan, site, "Another scan of this site kept running, so this one never started.")
                return
            raise self.retry(countdown=WAIT_SECONDS)
        lock_acquired = True

        other_running = db.execute(
            select(Scan.id).where(
                Scan.site_id == site.id, Scan.status == ScanStatus.RUNNING, Scan.id != scan.id
            ).limit(1)
        ).scalar_one_or_none()
        if other_running is not None:
            if self.request.retries >= self.max_retries:
                _mark_failed(db, scan, site, "Another scan of this site kept running, so this one never started.")
                return
            raise self.retry(countdown=WAIT_SECONDS)

        scan.status = ScanStatus.RUNNING
        scan.started_at = datetime.now(timezone.utc)
        db.commit()

        try:
            run_scan_pipeline(db, scan.id, site, scope_paths=scan.target_scope)
        except Exception as exc:  # noqa: BLE001 - an agent failure must not leave the scan hanging
            logger.exception("Scan %s failed", scan_id)
            db.rollback()
            _mark_failed(db, scan, site, str(exc))
            return

        scan.status = ScanStatus.COMPLETED
        scan.completed_at = datetime.now(timezone.utc)
        site.last_scanned_at = datetime.now(timezone.utc)
        db.commit()
    finally:
        if lock_acquired and site is not None:
            release_site_scan_lock(db, site.id)
        db.close()
