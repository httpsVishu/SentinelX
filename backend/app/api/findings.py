"""Finding endpoints (Admin only).

Backs the review queue, the Finding Review screen and the All findings page.
Approval queues the post-approval task (report, accountability, ticket) in a
Celery worker, after the decision is committed.

Route order matters: the fixed path /findings/pending-review must be declared
before /findings/{finding_id}.
"""
import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.rbac import require_admin
from app.database import get_db
from app.models.enums import FindingStatus, ReviewDecision
from app.models.user import User
from app.schemas.finding import FindingListItem, FindingRead, FindingReviewCreate
from app.services import finding_service
from app.tasks.approval_tasks import run_post_approval

router = APIRouter(prefix="/findings", tags=["findings"])


def _to_finding_read(db: Session, finding) -> FindingRead:
    return FindingRead(
        id=finding.id,
        site_id=finding.site_id,
        scan_id=finding.scan_id,
        title=finding.title,
        description=finding.description,
        severity=finding.severity,
        owasp_category=finding.owasp_category,
        confidence=float(finding.confidence),
        affected_endpoint=finding.affected_endpoint,
        status=finding.status,
        poc_summary=finding_service.decrypted_poc_summary(db, finding),
        plain_language_report=finding.plain_language_report,
        remediation_guidance=finding.remediation_guidance,
        validated_at=finding.validated_at,
        created_at=finding.created_at,
    )


@router.get("", response_model=list[FindingListItem])
def list_findings(
    site_id: uuid.UUID | None = None,
    status_filter: FindingStatus | None = Query(default=None, alias="status"),
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> list[FindingListItem]:
    return finding_service.list_findings(db, current_user.department_id, site_id, status_filter)


@router.get("/pending-review", response_model=list[FindingRead])
def list_pending_review(current_user: User = Depends(require_admin), db: Session = Depends(get_db)) -> list[FindingRead]:
    findings = finding_service.list_pending_review(db, current_user.department_id)
    return [_to_finding_read(db, f) for f in findings]


@router.get("/{finding_id}", response_model=FindingRead)
def get_finding(finding_id: uuid.UUID, current_user: User = Depends(require_admin), db: Session = Depends(get_db)) -> FindingRead:
    finding = finding_service.get_finding(db, finding_id, current_user.department_id)
    return _to_finding_read(db, finding)


@router.post("/{finding_id}/review", response_model=FindingRead)
def review_finding(
    finding_id: uuid.UUID, data: FindingReviewCreate,
    current_user: User = Depends(require_admin), db: Session = Depends(get_db),
) -> FindingRead:
    finding = finding_service.review_finding(db, finding_id, current_user.department_id, data, current_user.id)

    if data.decision == ReviewDecision.APPROVE:
        # After the commit above, so the worker sees the APPROVED status.
        run_post_approval.delay(str(finding.id), str(current_user.department_id))

    return _to_finding_read(db, finding)