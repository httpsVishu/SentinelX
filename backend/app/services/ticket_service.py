"""TicketService: ticket creation, assignment and deadline override, vendor
remediation and lifecycle transitions.

Invariants enforced here:
  - A ticket is created only from an APPROVED finding (Accountability Agent).
  - A Vendor can never change a deadline: no vendor-facing function takes one.
  - "Mark as fixed" never closes a ticket. submit_remediation() only moves it
    to FIX_SUBMITTED_PENDING_VERIFICATION. Closing happens only in
    record_verification_result(), after a real re-scan, and only for a ticket
    that is waiting on one.
"""
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.rbac import assert_vendor_owns_resource
from app.core.sla import calculate_deadline
from app.models.enums import AuditAction, DeadlineSource, ScanStatus, TicketStatus, VerificationResult
from app.models.finding import Finding
from app.models.scan import Scan
from app.models.site import Site
from app.models.ticket import RemediationSubmission, Ticket, VerificationRecord
from app.models.user import User
from app.schemas.ticket import RemediationSubmissionCreate, TicketAssignUpdate
from app.services import audit_service, vendor_service

# A queued or running re-scan older than this is treated as stuck (for example
# after a worker crash), so it no longer blocks a new one.
RESCAN_STALE_AFTER = timedelta(minutes=30)


class InvalidTicketTransition(Exception):
    """A status change that the ticket's current state does not allow."""


@dataclass
class AssignmentResult:
    ticket: Ticket
    vendor_changed: bool
    deadline_changed: bool


def create_ticket_from_approved_finding(
    db: Session, finding: Finding, department_id: uuid.UUID, actor_id: uuid.UUID | None = None
) -> Ticket:
    """Called once a finding is APPROVED. Uses the site's mapped vendor and
    the SLA formula in effect now. With no vendor the ticket starts
    UNASSIGNED (SRS 4.5-3 A1). Safe to call twice for the same finding."""
    existing = db.execute(select(Ticket).where(Ticket.finding_id == finding.id)).scalar_one_or_none()
    if existing is not None:
        return existing

    site = db.execute(select(Site).where(Site.id == finding.site_id)).scalar_one()
    suggested_deadline, _config = calculate_deadline(db, department_id, finding.severity)

    ticket = Ticket(
        finding_id=finding.id,
        site_id=finding.site_id,
        vendor_id=site.vendor_id,
        severity=finding.severity,
        status=TicketStatus.UNASSIGNED if site.vendor_id is None else TicketStatus.OPEN,
        deadline=suggested_deadline,
        suggested_deadline=suggested_deadline,
        deadline_source=DeadlineSource.AUTO,
    )
    db.add(ticket)
    db.flush()
    audit_service.record(
        db, action=AuditAction.TICKET_CREATED, entity_type="ticket",
        entity_id=ticket.id, actor_id=actor_id,
        metadata={"finding_id": str(finding.id), "vendor_id": str(site.vendor_id) if site.vendor_id else None},
    )
    db.commit()
    db.refresh(ticket)
    return ticket


def get_ticket(db: Session, ticket_id: uuid.UUID, department_id: uuid.UUID) -> Ticket:
    stmt = (
        select(Ticket)
        .join(Site, Ticket.site_id == Site.id)
        .where(Ticket.id == ticket_id, Site.department_id == department_id)
    )
    ticket = db.execute(stmt).scalar_one_or_none()
    if ticket is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ticket not found.")
    return ticket


def list_tickets(db: Session, department_id: uuid.UUID) -> list[Ticket]:
    stmt = (
        select(Ticket)
        .join(Site, Ticket.site_id == Site.id)
        .where(Site.department_id == department_id)
        .order_by(Ticket.created_at.desc())
    )
    return list(db.execute(stmt).scalars().all())


def list_vendor_tickets(db: Session, vendor_id: uuid.UUID) -> list[Ticket]:
    stmt = select(Ticket).where(Ticket.vendor_id == vendor_id).order_by(Ticket.created_at.desc())
    return list(db.execute(stmt).scalars().all())


def get_vendor_ticket(db: Session, ticket_id: uuid.UUID, current_user: User) -> Ticket:
    """Vendor-scoped fetch. assert_vendor_owns_resource is the backend
    guarantee that a vendor cannot read another vendor's ticket by ID."""
    ticket = db.execute(select(Ticket).where(Ticket.id == ticket_id)).scalar_one_or_none()
    if ticket is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ticket not found.")
    assert_vendor_owns_resource(current_user, ticket.vendor_id)
    return ticket


def assign_ticket(
    db: Session, ticket_id: uuid.UUID, department_id: uuid.UUID, data: TicketAssignUpdate, actor_id: uuid.UUID
) -> AssignmentResult:
    """Admin confirms or overrides the proposed vendor and deadline (SRS 4.3-4).
    Every check runs before anything on the ticket is changed. The result says
    what actually changed, so the caller alerts the vendor only when it did."""
    ticket = get_ticket(db, ticket_id, department_id)

    if ticket.status not in (TicketStatus.UNASSIGNED, TicketStatus.OPEN):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Ticket is in status '{ticket.status.value}' and cannot be reassigned.",
        )

    override = data.deadline_override
    if override is not None and override.tzinfo is None:
        override = override.replace(tzinfo=timezone.utc)  # a deadline without a zone is read as UTC

    override_reason = (data.override_reason or "").strip()
    if override is not None and not override_reason:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A reason is required when overriding the deadline.",
        )

    if data.vendor_id is not None:
        # 404 if the vendor is not in this admin's department.
        vendor_service.get_vendor(db, data.vendor_id, department_id)

    vendor_id = data.vendor_id or ticket.vendor_id
    if vendor_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot confirm a ticket with no vendor mapped. Map a vendor to the site or specify vendor_id.",
        )

    vendor_changed = vendor_id != ticket.vendor_id
    deadline_changed = override is not None and override != ticket.deadline

    ticket.vendor_id = vendor_id
    ticket.status = TicketStatus.OPEN

    if override is not None:
        ticket.deadline = override
        ticket.deadline_source = DeadlineSource.OVERRIDE
        ticket.override_reason = override_reason
        audit_service.record(
            db, action=AuditAction.TICKET_DEADLINE_OVERRIDDEN, entity_type="ticket",
            entity_id=ticket.id, actor_id=actor_id,
            metadata={"new_deadline": override.isoformat(), "reason": override_reason},
        )

    if vendor_changed:
        audit_service.record(
            db, action=AuditAction.TICKET_VENDOR_ASSIGNED, entity_type="ticket",
            entity_id=ticket.id, actor_id=actor_id, metadata={"vendor_id": str(vendor_id)},
        )

    db.commit()
    db.refresh(ticket)
    return AssignmentResult(ticket=ticket, vendor_changed=vendor_changed, deadline_changed=deadline_changed)


def submit_remediation(
    db: Session, ticket_id: uuid.UUID, current_user: User, data: RemediationSubmissionCreate
) -> Ticket:
    """Vendor reports a fix. Does not close the ticket. It moves to
    FIX_SUBMITTED_PENDING_VERIFICATION, and the API layer then queues the
    re-scan (kept out of here to avoid an import cycle with the tasks)."""
    ticket = get_vendor_ticket(db, ticket_id, current_user)

    if ticket.status not in (TicketStatus.OPEN, TicketStatus.OVERDUE, TicketStatus.FIX_FAILED_REOPENED):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Ticket is in status '{ticket.status.value}' and cannot be marked as fixed.",
        )

    db.add(RemediationSubmission(ticket_id=ticket.id, vendor_user_id=current_user.id, note=data.note))
    ticket.status = TicketStatus.FIX_SUBMITTED_PENDING_VERIFICATION

    audit_service.record(
        db, action=AuditAction.REMEDIATION_SUBMITTED, entity_type="ticket",
        entity_id=ticket.id, actor_id=current_user.id,
    )
    db.commit()
    db.refresh(ticket)
    return ticket


def request_reverification(
    db: Session, ticket_id: uuid.UUID, department_id: uuid.UUID, actor_id: uuid.UUID
) -> Ticket:
    """Admin asks for another re-scan of a ticket whose last one did not
    finish. The API layer queues the task after this commits. Refused while a
    re-scan of the same ticket is already queued or running."""
    ticket = get_ticket(db, ticket_id, department_id)

    if ticket.status != TicketStatus.FIX_SUBMITTED_PENDING_VERIFICATION:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Only a ticket whose fix is waiting for a re-scan can be checked again.",
        )

    live_rescan = db.execute(
        select(Scan.id).where(
            Scan.verification_ticket_id == ticket.id,
            Scan.status.in_([ScanStatus.QUEUED, ScanStatus.RUNNING]),
            Scan.queued_at >= datetime.now(timezone.utc) - RESCAN_STALE_AFTER,
        ).limit(1)
    ).first()
    if live_rescan is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A re-scan of this ticket is already running. Wait for it to finish.",
        )

    audit_service.record(
        db, action=AuditAction.SCAN_TRIGGERED, entity_type="ticket",
        entity_id=ticket.id, actor_id=actor_id, metadata={"reason": "manual re-verification"},
    )
    db.commit()
    db.refresh(ticket)
    return ticket


def record_verification_result(
    db: Session, ticket_id: uuid.UUID, scan_id: uuid.UUID, result: VerificationResult, notes: str | None = None
) -> Ticket:
    """Called by the verification pipeline after a re-scan. The only place a
    ticket can reach VERIFIED_CLOSED, and only from FIX_SUBMITTED_PENDING_VERIFICATION,
    so a ticket cannot be closed without a Vendor claim and a passed re-scan."""
    ticket = db.execute(select(Ticket).where(Ticket.id == ticket_id)).scalar_one()

    if ticket.status != TicketStatus.FIX_SUBMITTED_PENDING_VERIFICATION:
        raise InvalidTicketTransition(
            f"Ticket is '{ticket.status.value}'. Only a ticket with a submitted fix can be verified."
        )

    db.add(VerificationRecord(ticket_id=ticket.id, scan_id=scan_id, result=result, notes=notes))
    # Write the verification row before the ticket changes, so the database
    # closure rule sees the passed record whenever it runs.
    db.flush()

    if result == VerificationResult.PASSED:
        ticket.status = TicketStatus.VERIFIED_CLOSED
        ticket.closed_at = datetime.now(timezone.utc)
        audit_service.record(db, action=AuditAction.VERIFICATION_PASSED, entity_type="ticket", entity_id=ticket.id)
        audit_service.record(db, action=AuditAction.TICKET_CLOSED, entity_type="ticket", entity_id=ticket.id)
    else:
        ticket.status = TicketStatus.FIX_FAILED_REOPENED
        audit_service.record(db, action=AuditAction.VERIFICATION_FAILED, entity_type="ticket", entity_id=ticket.id)

    db.commit()
    db.refresh(ticket)
    return ticket


def mark_overdue_if_past_deadline(db: Session, ticket: Ticket) -> bool:
    """Used by the daily deadline check. Moves an OPEN ticket past its deadline
    to OVERDUE and records when. Returns True if it did. The alert sent for it
    is the record of the event."""
    if ticket.status != TicketStatus.OPEN:
        return False
    now = datetime.now(timezone.utc)
    if ticket.deadline >= now:
        return False

    ticket.status = TicketStatus.OVERDUE
    if ticket.became_overdue_at is None:
        ticket.became_overdue_at = now
    db.commit()
    return True


def list_open_tickets_past_deadline(db: Session) -> list[Ticket]:
    stmt = select(Ticket).where(
        Ticket.status == TicketStatus.OPEN,
        Ticket.deadline < datetime.now(timezone.utc),
    )
    return list(db.execute(stmt).scalars().all())