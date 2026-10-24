"""Vendor management endpoints — Admin manages vendors; a Vendor user can
only read their own vendor record (never list or view others)."""
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.rbac import require_admin, require_any_role
from app.database import get_db
from app.models.enums import UserRole
from app.models.user import User
from app.schemas.vendor import VendorCreate, VendorRead, VendorUpdate
from app.services import vendor_service

router = APIRouter(prefix="/vendors", tags=["vendors"])


@router.post("", response_model=VendorRead, status_code=201)
def create_vendor(data: VendorCreate, current_user: User = Depends(require_admin), db: Session = Depends(get_db)) -> VendorRead:
    return vendor_service.create_vendor(db, current_user.department_id, data, current_user.id)


@router.get("", response_model=list[VendorRead])
def list_vendors(current_user: User = Depends(require_admin), db: Session = Depends(get_db)) -> list[VendorRead]:
    return vendor_service.list_vendors(db, current_user.department_id)


@router.get("/{vendor_id}", response_model=VendorRead)
def get_vendor(vendor_id: uuid.UUID, current_user: User = Depends(require_any_role), db: Session = Depends(get_db)) -> VendorRead:
    # A Vendor user may only fetch their own vendor record.
    if current_user.role == UserRole.VENDOR and current_user.vendor_id != vendor_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You do not have permission to access this resource.")
    return vendor_service.get_vendor(db, vendor_id, current_user.department_id)


@router.patch("/{vendor_id}", response_model=VendorRead)
def update_vendor(
    vendor_id: uuid.UUID, data: VendorUpdate,
    current_user: User = Depends(require_admin), db: Session = Depends(get_db),
) -> VendorRead:
    return vendor_service.update_vendor(db, vendor_id, current_user.department_id, data)


@router.delete("/{vendor_id}", status_code=204)
def delete_vendor(vendor_id: uuid.UUID, current_user: User = Depends(require_admin), db: Session = Depends(get_db)) -> None:
    vendor_service.delete_vendor(db, vendor_id, current_user.department_id)