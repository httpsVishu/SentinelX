"""Site management endpoints (Admin only).

Covers CRUD plus the discrete config actions from SRS 2.1.8 (schedule,
exclusions, vendor mapping, active/paused) and the authorization-record
workflow for restricted-domain sites.
"""
import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.rbac import require_admin
from app.database import get_db
from app.models.user import User
from app.schemas.site import (
    AuthorizationRecordCreate,
    AuthorizationRecordRead,
    SiteCreate,
    SiteRead,
    SiteUpdateActive,
    SiteUpdateExclusions,
    SiteUpdateSchedule,
    SiteUpdateVendor,
)
from app.services import authorization_service, site_service

router = APIRouter(prefix="/sites", tags=["sites"])


@router.post("", response_model=SiteRead, status_code=201)
def create_site(data: SiteCreate, current_user: User = Depends(require_admin), db: Session = Depends(get_db)) -> SiteRead:
    return site_service.create_site(db, current_user.department_id, data, current_user.id)


@router.get("", response_model=list[SiteRead])
def list_sites(current_user: User = Depends(require_admin), db: Session = Depends(get_db)) -> list[SiteRead]:
    return site_service.list_sites(db, current_user.department_id)


@router.get("/{site_id}", response_model=SiteRead)
def get_site(site_id: uuid.UUID, current_user: User = Depends(require_admin), db: Session = Depends(get_db)) -> SiteRead:
    return site_service.get_site(db, site_id, current_user.department_id)


@router.patch("/{site_id}/schedule", response_model=SiteRead)
def update_schedule(
    site_id: uuid.UUID, data: SiteUpdateSchedule,
    current_user: User = Depends(require_admin), db: Session = Depends(get_db),
) -> SiteRead:
    return site_service.update_schedule(db, site_id, current_user.department_id, data.scan_frequency_days, current_user.id)


@router.patch("/{site_id}/exclusions", response_model=SiteRead)
def update_exclusions(
    site_id: uuid.UUID, data: SiteUpdateExclusions,
    current_user: User = Depends(require_admin), db: Session = Depends(get_db),
) -> SiteRead:
    return site_service.update_exclusions(db, site_id, current_user.department_id, data.excluded_paths, current_user.id)


@router.patch("/{site_id}/vendor", response_model=SiteRead)
def update_vendor_mapping(
    site_id: uuid.UUID, data: SiteUpdateVendor,
    current_user: User = Depends(require_admin), db: Session = Depends(get_db),
) -> SiteRead:
    return site_service.update_vendor_mapping(db, site_id, current_user.department_id, data.vendor_id, current_user.id)


@router.patch("/{site_id}/active", response_model=SiteRead)
def update_active_state(
    site_id: uuid.UUID, data: SiteUpdateActive,
    current_user: User = Depends(require_admin), db: Session = Depends(get_db),
) -> SiteRead:
    return site_service.update_active_state(db, site_id, current_user.department_id, data.is_active)


@router.get("/{site_id}/authorization-records", response_model=list[AuthorizationRecordRead])
def list_authorization_records(
    site_id: uuid.UUID, current_user: User = Depends(require_admin), db: Session = Depends(get_db),
) -> list[AuthorizationRecordRead]:
    # get_site raises 404 when the site is not in the admin's department.
    site = site_service.get_site(db, site_id, current_user.department_id)
    return authorization_service.list_authorization_records(db, site.id)


@router.post("/{site_id}/authorization-records", response_model=AuthorizationRecordRead, status_code=201)
def add_authorization_record(
    site_id: uuid.UUID, data: AuthorizationRecordCreate,
    current_user: User = Depends(require_admin), db: Session = Depends(get_db),
) -> AuthorizationRecordRead:
    return site_service.add_authorization_record(db, site_id, current_user.department_id, data, current_user.id)