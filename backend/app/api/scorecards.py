"""Vendor scorecard endpoints — Admin views any vendor in their department;
Vendor views only their own."""
import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.rbac import require_admin, require_vendor
from app.database import get_db
from app.models.user import User
from app.schemas.scorecard import VendorScorecardRead
from app.services import scorecard_service, vendor_service

router = APIRouter(prefix="/scorecards", tags=["scorecards"])


@router.get("/mine", response_model=VendorScorecardRead)
def get_my_scorecard(current_user: User = Depends(require_vendor), db: Session = Depends(get_db)) -> VendorScorecardRead:
    return scorecard_service.compute_vendor_scorecard(db, current_user.vendor_id)


@router.get("/{vendor_id}", response_model=VendorScorecardRead)
def get_vendor_scorecard(
    vendor_id: uuid.UUID, current_user: User = Depends(require_admin), db: Session = Depends(get_db)
) -> VendorScorecardRead:
    vendor_service.get_vendor(db, vendor_id, current_user.department_id)  # 404s if not in department
    return scorecard_service.compute_vendor_scorecard(db, vendor_id)