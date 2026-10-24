"""Ticket endpoints: Admin (full visibility, assignment) and Vendor (own
tickets only, remediation).

Route order matters: the fixed path /tickets/mine must be declared before
/tickets/{ticket_id}, otherwise "mine" is captured as a ticket id.

Vendor routes return VendorTicketRead, which structurally omits raw exploit
and scanner-output fields (SRS 4.4-2).
"""
import uuid

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.rbac import require_admin, require_vendor
from app.database import get_db
from app.models.finding import Finding
from app.models.site import Site
from app.models.user import User
from app.schemas.ticket import (
    RemediationSubmissionCreate,
    TicketAssignUpdate,
    TicketListItem,
    TicketRead,
    VendorTicketRead,
)
from app.services import ticket_service
from app.tasks.notification_tasks import notify_vendor_of_ticket_change
from app.tasks.verification_tasks import run_verification_scan

router = APIRouter(prefix="/tickets", tags=["tickets"])


# ---- Vendor routes (declared first, see module docstring) ----

def _vendor_ticket_read(db: Session, ticket) -> VendorTicketRead:
    finding = db.execute(select(Finding).where(Finding.id == ticket.finding_id)).scalar_one()
    site = db.execute(select(Site).where(Site.id == ticket.site_id)).scalar_one()
    return VendorTicketRead(
        id=ticket.id,
        site_id=ticket.site_id,
        site_name=site.name,
        severity=ticket.severity,
        status=ticket.status,
        deadline=ticket.deadline,
        created_at=ticket.created_at,
        plain_language_report=finding.plain_language_report,
        remediation_guidance=finding.remediation_guidance,
        affected_endpoint=finding.affected_endpoint,
        remediation_submissions=list(ticket.remediation_submissions),
    )


@router.get("/mine", response_model=list[VendorTicketRead])
def list_my_tickets(current_user: User = Depends(require_vendor), db: Session = Depends(get_db)) -> list[VendorTicketRead]:
    tickets = ticket_service.list_vendor_tickets(db, current_user.vendor_id)
    return [_vendor_ticket_read(db, t) for t in tickets]


@router.get("/mine/{ticket_id}", response_model=VendorTicketRead)
def get_my_ticket(ticket_id: uuid.UUID, current_user: User = Depends(require_vendor), db: Session = Depends(get_db)) -> VendorTicketRead:
    ticket = ticket_service.get_vendor_ticket(db, ticket_id, current_user)
    return _vendor_ticket_read(db, ticket)


@router.post("/mine/{ticket_id}/remediate", response_model=VendorTicketRead)
def submit_remediation(
    ticket_id: uuid.UUID, data: RemediationSubmissionCreate,
    current_user: User = Depends(require_vendor), db: Session = Depends(get_db),
) -> VendorTicketRead:
    ticket = ticket_service.submit_remediation(db, ticket_id, current_user, data)
    run_verification_scan.delay(str(ticket.id))
    return _vendor_ticket_read(db, ticket)


# ---- Admin routes ----

@router.get("", response_model=list[TicketListItem])
def list_tickets(current_user: User = Depends(require_admin), db: Session = Depends(get_db)) -> list[TicketListItem]:
    return ticket_service.list_tickets(db, current_user.department_id)


@router.get("/{ticket_id}", response_model=TicketRead)
def get_ticket(ticket_id: uuid.UUID, current_user: User = Depends(require_admin), db: Session = Depends(get_db)) -> TicketRead:
    return ticket_service.get_ticket(db, ticket_id, current_user.department_id)


@router.post("/{ticket_id}/assign", response_model=TicketRead)
def assign_ticket(
    ticket_id: uuid.UUID, data: TicketAssignUpdate,
    current_user: User = Depends(require_admin), db: Session = Depends(get_db),
) -> TicketRead:
    result = ticket_service.assign_ticket(db, ticket_id, current_user.department_id, data, current_user.id)

    # A vendor change supersedes a deadline-change notice: the new owner needs
    # one clear assignment message containing the effective deadline.
    if result.vendor_changed:
        notify_vendor_of_ticket_change.delay(str(result.ticket.id), "assigned")
    elif result.deadline_changed:
        notify_vendor_of_ticket_change.delay(str(result.ticket.id), "deadline_changed")

    return result.ticket


@router.post("/{ticket_id}/reverify", response_model=TicketRead)
def reverify_ticket(
    ticket_id: uuid.UUID, current_user: User = Depends(require_admin), db: Session = Depends(get_db),
) -> TicketRead:
    """Run the re-scan again for a ticket whose last verification was inconclusive."""
    ticket = ticket_service.request_reverification(db, ticket_id, current_user.department_id, current_user.id)
    run_verification_scan.delay(str(ticket.id))
    return ticket
