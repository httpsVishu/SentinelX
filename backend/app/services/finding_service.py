"""FindingService: finding retrieval, decryption for display, and the Admin
Approve and Reject workflow.

Approving only marks the finding APPROVED and records the review. The ticket is
created afterwards by the approval task through the Accountability agent
(app/tasks/approval_tasks.py), so human sign-off and the accountability
pipeline stay separate steps, as the SRS describes them (4.3-3 and 4.5-3).
"""
import uuid

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.crypto import decrypt_text
from app.models.enums import AuditAction, FindingStatus, ReviewDecision
from app.models.finding import Finding, FindingReview
from app.models.site import Site
from app.schemas.finding import FindingReviewCreate
from app.services import audit_service


def list_pending_review(db: Session, department_id: uuid.UUID) -> list[Finding]:
    stmt = (
        select(Finding)
        .join(Site, Finding.site_id == Site.id)
        .where(Site.department_id == department_id, Finding.status == FindingStatus.PENDING_ADMIN_REVIEW)
        .order_by(Finding.severity, Finding.created_at)  # enum order: most severe first
    )
    return list(db.execute(stmt).scalars().all())


def list_findings(
    db: Session,
    department_id: uuid.UUID,
    site_id: uuid.UUID | None = None,
    status_filter: FindingStatus | None = None,
) -> list[Finding]:
    """Every finding in the department, newest first, whatever its status."""
    stmt = select(Finding).join(Site, Finding.site_id == Site.id).where(Site.department_id == department_id)
    if site_id is not None:
        stmt = stmt.where(Finding.site_id == site_id)
    if status_filter is not None:
        stmt = stmt.where(Finding.status == status_filter)
    return list(db.execute(stmt.order_by(Finding.created_at.desc())).scalars().all())


def get_finding(db: Session, finding_id: uuid.UUID, department_id: uuid.UUID) -> Finding:
    stmt = (
        select(Finding)
        .join(Site, Finding.site_id == Site.id)
        .where(Finding.id == finding_id, Site.department_id == department_id)
    )
    finding = db.execute(stmt).scalar_one_or_none()
    if finding is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Finding not found.")
    return finding


def decrypted_poc_summary(db: Session, finding: Finding) -> str | None:
    return decrypt_text(db, finding.poc_summary_encrypted)


def review_finding(
    db: Session, finding_id: uuid.UUID, department_id: uuid.UUID, data: FindingReviewCreate, reviewer_id: uuid.UUID
) -> Finding:
    finding = get_finding(db, finding_id, department_id)

    if finding.status != FindingStatus.PENDING_ADMIN_REVIEW:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Finding is in status '{finding.status.value}' and is not awaiting review.",
        )

    reason = (data.reason or "").strip() or None
    if data.decision == ReviewDecision.REJECT and reason is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A reason is required when rejecting a finding.",
        )

    db.add(FindingReview(finding_id=finding.id, reviewer_id=reviewer_id, decision=data.decision, reason=reason))

    if data.decision == ReviewDecision.APPROVE:
        finding.status = FindingStatus.APPROVED
        audit_service.record(
            db, action=AuditAction.FINDING_APPROVED, entity_type="finding",
            entity_id=finding.id, actor_id=reviewer_id,
        )
    else:
        finding.status = FindingStatus.REJECTED
        audit_service.record(
            db, action=AuditAction.FINDING_REJECTED, entity_type="finding",
            entity_id=finding.id, actor_id=reviewer_id, metadata={"reason": reason},
        )

    db.commit()
    db.refresh(finding)
    return finding