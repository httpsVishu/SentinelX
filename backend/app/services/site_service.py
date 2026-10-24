"""SiteService — CRUD and configuration logic for Site records.

Covers the "Site Adaptation Requirements" from SRS 2.1.8: scan frequency,
excluded paths, responsible vendor, active/paused state. Each discrete
config action is its own function (matching the discrete SiteUpdate*
schemas) so each is individually auditable and matches the SRS's "Scan
Schedule Configuration Screen" / exclusion-editing flow.
"""
import uuid

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.authorization_record import AuthorizationRecord
from app.models.enums import AuditAction
from app.models.site import Site
from app.models.vendor import Vendor
from app.schemas.site import AuthorizationRecordCreate, SiteCreate
from app.services import audit_service
from app.services.authorization_service import url_is_restricted_domain


def create_site(db: Session, department_id: uuid.UUID, data: SiteCreate, actor_id: uuid.UUID) -> Site:
    if data.vendor_id is not None:
        vendor = db.execute(
            select(Vendor).where(Vendor.id == data.vendor_id, Vendor.department_id == department_id)
        ).scalar_one_or_none()
        if vendor is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="vendor_id does not exist in this department.")

    # Defense in depth: if the Admin didn't flag is_gov_in but the URL
    # matches a restricted suffix, flag it automatically rather than
    # silently trusting client input.
    is_gov_in = data.is_gov_in or url_is_restricted_domain(data.url)

    site = Site(
        department_id=department_id,
        name=data.name,
        url=data.url,
        vendor_id=data.vendor_id,
        scan_frequency_days=data.scan_frequency_days,
        excluded_paths=data.excluded_paths,
        is_gov_in=is_gov_in,
    )
    db.add(site)
    db.flush()
    audit_service.record(
        db, action=AuditAction.SITE_CREATED, entity_type="site",
        entity_id=site.id, actor_id=actor_id, metadata={"action": "created", "name": site.name},
    )
    db.commit()
    db.refresh(site)
    return site


def list_sites(db: Session, department_id: uuid.UUID) -> list[Site]:
    stmt = select(Site).where(Site.department_id == department_id).order_by(Site.name)
    return list(db.execute(stmt).scalars().all())


def get_site(db: Session, site_id: uuid.UUID, department_id: uuid.UUID) -> Site:
    stmt = select(Site).where(Site.id == site_id, Site.department_id == department_id)
    site = db.execute(stmt).scalar_one_or_none()
    if site is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Site not found.")
    return site


def update_schedule(db: Session, site_id: uuid.UUID, department_id: uuid.UUID, frequency_days: int, actor_id: uuid.UUID) -> Site:
    site = get_site(db, site_id, department_id)
    site.scan_frequency_days = frequency_days
    audit_service.record(
        db, action=AuditAction.SITE_SCHEDULE_UPDATED, entity_type="site",
        entity_id=site.id, actor_id=actor_id, metadata={"scan_frequency_days": frequency_days},
    )
    db.commit()
    db.refresh(site)
    return site


def update_exclusions(db: Session, site_id: uuid.UUID, department_id: uuid.UUID, excluded_paths: list[str], actor_id: uuid.UUID) -> Site:
    site = get_site(db, site_id, department_id)

    if "/" in excluded_paths or "*" in excluded_paths:
        # SRS 4.3-5 A1: Admin tries to exclude the whole site — the service
        # layer still allows it (the warning/confirmation step is a
        # frontend concern) but this is where a stricter MVP could reject
        # it outright. We permit it here since the SRS frames it as a
        # confirm-and-proceed flow, not a hard block.
        pass

    site.excluded_paths = excluded_paths
    audit_service.record(
        db, action=AuditAction.SITE_EXCLUSIONS_UPDATED, entity_type="site",
        entity_id=site.id, actor_id=actor_id, metadata={"excluded_paths": excluded_paths},
    )
    db.commit()
    db.refresh(site)
    return site


def update_vendor_mapping(db: Session, site_id: uuid.UUID, department_id: uuid.UUID, vendor_id: uuid.UUID | None, actor_id: uuid.UUID) -> Site:
    site = get_site(db, site_id, department_id)
    if vendor_id is not None:
        vendor = db.execute(
            select(Vendor).where(Vendor.id == vendor_id, Vendor.department_id == department_id)
        ).scalar_one_or_none()
        if vendor is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="vendor_id does not exist in this department.")
    site.vendor_id = vendor_id
    db.commit()
    db.refresh(site)
    return site


def update_active_state(db: Session, site_id: uuid.UUID, department_id: uuid.UUID, is_active: bool) -> Site:
    site = get_site(db, site_id, department_id)
    site.is_active = is_active
    db.commit()
    db.refresh(site)
    return site


def add_authorization_record(
    db: Session, site_id: uuid.UUID, department_id: uuid.UUID, data: AuthorizationRecordCreate, actor_id: uuid.UUID
) -> AuthorizationRecord:
    site = get_site(db, site_id, department_id)
    record = AuthorizationRecord(
        site_id=site.id,
        document_reference=data.document_reference,
        notes=data.notes,
        granted_by_user_id=actor_id,
        granted_at=data.granted_at,
    )
    db.add(record)
    audit_service.record(
        db, action=AuditAction.AUTHORIZATION_RECORD_ADDED, entity_type="site",
        entity_id=site.id, actor_id=actor_id, metadata={"document_reference": data.document_reference},
    )
    db.commit()
    db.refresh(record)
    return record