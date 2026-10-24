"""Alert endpoints. Admins read the log for all department admins. Vendors
read only their own alerts."""
import uuid

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.rbac import require_admin, require_vendor
from app.database import get_db
from app.models.enums import AlertLevel, AlertTriggerType, UserRole
from app.models.user import User
from app.schemas.alert import AlertRead
from app.services import alert_service

router = APIRouter(prefix="/alerts", tags=["alerts"])


@router.get("", response_model=list[AlertRead])
def list_department_alerts(
    site_id: uuid.UUID | None = None, level: AlertLevel | None = None, trigger_type: AlertTriggerType | None = None,
    current_user: User = Depends(require_admin), db: Session = Depends(get_db),
) -> list[AlertRead]:
    admin_ids = db.execute(
        select(User.id).where(User.department_id == current_user.department_id, User.role == UserRole.ADMIN)
    ).scalars().all()
    return alert_service.list_alerts_for_department(db, list(admin_ids), site_id, level, trigger_type)


@router.get("/mine", response_model=list[AlertRead])
def list_my_alerts(
    site_id: uuid.UUID | None = None, level: AlertLevel | None = None, trigger_type: AlertTriggerType | None = None,
    current_user: User = Depends(require_vendor), db: Session = Depends(get_db),
) -> list[AlertRead]:
    alerts = alert_service.list_alerts_for_recipient(db, current_user.id, site_id, level, trigger_type)
    # A delivery error can name mail or SMS gateway details. Admins see it. Vendors do not.
    return [AlertRead.model_validate(alert).model_copy(update={"delivery_error": None}) for alert in alerts]