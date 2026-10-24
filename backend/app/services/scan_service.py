"""ScanService — Scan creation with duplicate-run prevention and
authorization enforcement.

Per SRS 4.5-1 A2: if a scan for the same site is already running (status
QUEUED or RUNNING), a new trigger is queued rather than run in parallel —
implemented here as simply reusing/creating a new QUEUED Scan row while an
earlier one is still in flight; the Celery task layer (app/tasks/scan_tasks.py)
is responsible for actually serializing execution per site so two QUEUED
scans for the same site never run their agent pipelines concurrently.
"""
import uuid

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.enums import AuditAction, ScanStatus, ScanTriggerType
from app.models.scan import Scan
from app.models.site import Site
from app.services import audit_service
from app.services.authorization_service import ScanNotAuthorizedError, assert_scan_is_authorized


def site_has_scan_in_flight(db: Session, site_id: uuid.UUID) -> bool:
    stmt = select(Scan.id).where(
        Scan.site_id == site_id,
        Scan.status.in_([ScanStatus.QUEUED, ScanStatus.RUNNING]),
    ).limit(1)
    return db.execute(stmt).scalar_one_or_none() is not None


def trigger_scan(
    db: Session,
    site: Site,
    trigger_type: ScanTriggerType,
    triggered_by_user_id: uuid.UUID | None = None,
    target_scope: list[str] | None = None,
    verification_ticket_id: uuid.UUID | None = None,
) -> Scan:
    """Create a new Scan row for a site. Raises ScanNotAuthorizedError if
    the site requires a written authorization record that doesn't exist.
    If a scan is already in flight for this site, the new scan is still
    created (status QUEUED) — the Celery task picking it up is responsible
    for waiting its turn rather than running concurrently with the
    in-flight one."""
    if not site.is_active:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Site is paused; activate it before triggering a scan.",
        )

    try:
        assert_scan_is_authorized(db, site)
    except ScanNotAuthorizedError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc

    already_running = site_has_scan_in_flight(db, site.id)

    scan = Scan(
        site_id=site.id,
        trigger_type=trigger_type,
        status=ScanStatus.QUEUED,
        target_scope=target_scope,
        verification_ticket_id=verification_ticket_id,
        triggered_by_user_id=triggered_by_user_id,
    )
    db.add(scan)
    db.flush()

    audit_service.record(
        db,
        action=AuditAction.SCAN_QUEUED_DUPLICATE if already_running else AuditAction.SCAN_TRIGGERED,
        entity_type="scan",
        entity_id=scan.id,
        actor_id=triggered_by_user_id,
        metadata={"site_id": str(site.id), "trigger_type": trigger_type.value, "queued_behind_running_scan": already_running},
    )
    db.commit()
    db.refresh(scan)
    return scan


def get_scan(db: Session, scan_id: uuid.UUID, department_id: uuid.UUID) -> Scan:
    stmt = (
        select(Scan)
        .join(Site, Scan.site_id == Site.id)
        .where(Scan.id == scan_id, Site.department_id == department_id)
    )
    scan = db.execute(stmt).scalar_one_or_none()
    if scan is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Scan not found.")
    return scan


def list_scans(db: Session, department_id: uuid.UUID, site_id: uuid.UUID | None = None) -> list[Scan]:
    stmt = select(Scan).join(Site, Scan.site_id == Site.id).where(Site.department_id == department_id)
    if site_id is not None:
        stmt = stmt.where(Scan.site_id == site_id)
    stmt = stmt.order_by(Scan.queued_at.desc())
    return list(db.execute(stmt).scalars().all())