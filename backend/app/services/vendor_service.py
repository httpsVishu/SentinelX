"""VendorService — CRUD and lookup logic for Vendor records.

Kept deliberately thin since Vendor has few invariants beyond "must have a
contact_email" (already enforced at the schema/model level). The main
reason this service exists rather than inlining logic in the router is to
keep audit logging and future business rules (e.g. preventing deletion of a
vendor with open tickets) in one place.
"""
import uuid

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.enums import AuditAction
from app.models.ticket import Ticket
from app.models.vendor import Vendor
from app.schemas.vendor import VendorCreate, VendorUpdate
from app.services import audit_service


def create_vendor(db: Session, department_id: uuid.UUID, data: VendorCreate, actor_id: uuid.UUID) -> Vendor:
    vendor = Vendor(
        department_id=department_id,
        name=data.name,
        contact_email=data.contact_email,
        contact_phone=data.contact_phone,
    )
    db.add(vendor)
    db.flush()
    audit_service.record(
        db, action=AuditAction.VENDOR_CREATED, entity_type="vendor",
        entity_id=vendor.id, actor_id=actor_id, metadata={"action": "created", "name": vendor.name},
    )
    db.commit()
    db.refresh(vendor)
    return vendor


def list_vendors(db: Session, department_id: uuid.UUID) -> list[Vendor]:
    stmt = select(Vendor).where(Vendor.department_id == department_id).order_by(Vendor.name)
    return list(db.execute(stmt).scalars().all())


def get_vendor(db: Session, vendor_id: uuid.UUID, department_id: uuid.UUID) -> Vendor:
    stmt = select(Vendor).where(Vendor.id == vendor_id, Vendor.department_id == department_id)
    vendor = db.execute(stmt).scalar_one_or_none()
    if vendor is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Vendor not found.")
    return vendor


def update_vendor(db: Session, vendor_id: uuid.UUID, department_id: uuid.UUID, data: VendorUpdate) -> Vendor:
    vendor = get_vendor(db, vendor_id, department_id)
    if data.name is not None:
        vendor.name = data.name
    if data.contact_email is not None:
        vendor.contact_email = data.contact_email
    if data.contact_phone is not None:
        vendor.contact_phone = data.contact_phone
    db.commit()
    db.refresh(vendor)
    return vendor


def delete_vendor(db: Session, vendor_id: uuid.UUID, department_id: uuid.UUID) -> None:
    vendor = get_vendor(db, vendor_id, department_id)

    ticket_exists = db.execute(
        select(Ticket.id).where(
            Ticket.vendor_id == vendor.id,
        ).limit(1)
    ).scalar_one_or_none()

    if ticket_exists is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cannot delete a vendor with ticket history. Retain the vendor for audit history.",
        )

    db.delete(vendor)
    db.commit()
