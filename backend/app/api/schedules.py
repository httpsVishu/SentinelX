"""SLA configuration endpoints (Admin only).

GET returns the currently-effective department-wide SLA config. PUT creates
a NEW SLAConfig row with effective_from=now (it never mutates an existing
row), which preserves the versioned history from app/models/sla_config.py
and app/core/sla.py. Tickets already created keep the deadline they were
given.
"""
from datetime import datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.core.rbac import require_admin
from app.core.sla import get_active_sla_config
from app.database import get_db
from app.models.sla_config import SLAConfig
from app.models.user import User

router = APIRouter(prefix="/schedules", tags=["schedules"])


class SLAConfigRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    critical_days: int
    high_days: int
    medium_days: int
    low_days: int
    effective_from: datetime


class SLAConfigUpdate(BaseModel):
    critical_days: int = Field(ge=1, le=365)
    high_days: int = Field(ge=1, le=365)
    medium_days: int = Field(ge=1, le=365)
    low_days: int = Field(ge=1, le=365)


@router.get("/sla", response_model=SLAConfigRead)
def get_sla_config(current_user: User = Depends(require_admin), db: Session = Depends(get_db)) -> SLAConfig:
    return get_active_sla_config(db, current_user.department_id)


@router.put("/sla", response_model=SLAConfigRead)
def update_sla_config(
    data: SLAConfigUpdate, current_user: User = Depends(require_admin), db: Session = Depends(get_db)
) -> SLAConfig:
    new_config = SLAConfig(
        department_id=current_user.department_id,
        critical_days=data.critical_days,
        high_days=data.high_days,
        medium_days=data.medium_days,
        low_days=data.low_days,
    )
    db.add(new_config)
    db.commit()
    db.refresh(new_config)
    return new_config