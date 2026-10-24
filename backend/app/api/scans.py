"""Scan trigger and read endpoints — Admin only."""
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.rbac import require_admin
from app.database import get_db
from app.models.enums import ScanTriggerType
from app.models.user import User
from app.schemas.scan import AgentExecutionRead, ScanRead, ScanTriggerRequest
from app.services import scan_service, site_service
from app.services.authorization_service import ScanNotAuthorizedError
from app.tasks.scan_tasks import execute_scan

router = APIRouter(prefix="/scans", tags=["scans"])


@router.post("/{site_id}/trigger", response_model=ScanRead, status_code=201)
def trigger_manual_scan(
    site_id: uuid.UUID, data: ScanTriggerRequest | None = None,
    current_user: User = Depends(require_admin), db: Session = Depends(get_db),
) -> ScanRead:
    site = site_service.get_site(db, site_id, current_user.department_id)
    try:
        scan = scan_service.trigger_scan(db, site, ScanTriggerType.MANUAL, triggered_by_user_id=current_user.id)
    except ScanNotAuthorizedError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc

    execute_scan.delay(str(scan.id))
    return scan


@router.get("", response_model=list[ScanRead])
def list_scans(
    site_id: uuid.UUID | None = None,
    current_user: User = Depends(require_admin), db: Session = Depends(get_db),
) -> list[ScanRead]:
    return scan_service.list_scans(db, current_user.department_id, site_id)


@router.get("/{scan_id}", response_model=ScanRead)
def get_scan(scan_id: uuid.UUID, current_user: User = Depends(require_admin), db: Session = Depends(get_db)) -> ScanRead:
    return scan_service.get_scan(db, scan_id, current_user.department_id)


@router.get("/{scan_id}/executions", response_model=list[AgentExecutionRead])
def get_scan_executions(scan_id: uuid.UUID, current_user: User = Depends(require_admin), db: Session = Depends(get_db)):
    scan = scan_service.get_scan(db, scan_id, current_user.department_id)
    return scan.agent_executions