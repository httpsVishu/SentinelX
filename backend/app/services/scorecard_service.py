"""ScorecardService: computes vendor performance from ticket history.

Everything is worked out on demand from verified ticket data (SRS 4.3-6: scores
come from verified data, not the vendor's own report). There is deliberately no
write path here, so scorecards cannot be edited (SRS 3.6).

Definitions:
  fix rate          verified-closed tickets, out of tickets that are closed,
                    overdue or reopened
  missed deadline   a ticket that is overdue now, went overdue at any point, or
                    whose first fix report came after its deadline
  response time     ticket opened to the first fix report, averaged
  repeat            a site and endpoint that a vendor had verified-closed more
                    than once (each close after the first is one repeat)
"""
import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.enums import TicketStatus
from app.models.finding import Finding
from app.models.ticket import RemediationSubmission, Ticket
from app.models.vendor import Vendor
from app.schemas.scorecard import VendorScorecardRead

_COUNTED_FOR_FIX_RATE = {TicketStatus.VERIFIED_CLOSED, TicketStatus.OVERDUE, TicketStatus.FIX_FAILED_REOPENED}


def compute_vendor_scorecard(db: Session, vendor_id: uuid.UUID) -> VendorScorecardRead:
    vendor = db.execute(select(Vendor).where(Vendor.id == vendor_id)).scalar_one()

    rows = db.execute(
        select(Ticket, Finding.site_id, Finding.affected_endpoint)
        .join(Finding, Finding.id == Ticket.finding_id)
        .where(Ticket.vendor_id == vendor_id)
    ).all()
    tickets = [row[0] for row in rows]
    ids = [ticket.id for ticket in tickets]

    first_report: dict[uuid.UUID, object] = {}
    if ids:
        first_report = dict(
            db.execute(
                select(RemediationSubmission.ticket_id, func.min(RemediationSubmission.submitted_at))
                .where(RemediationSubmission.ticket_id.in_(ids))
                .group_by(RemediationSubmission.ticket_id)
            ).all()
        )

    closed = [t for t in tickets if t.status == TicketStatus.VERIFIED_CLOSED]
    overdue_now = [t for t in tickets if t.status == TicketStatus.OVERDUE]
    counted = [t for t in tickets if t.status in _COUNTED_FOR_FIX_RATE]
    fix_rate = len(closed) / len(counted) if counted else 0.0

    def missed(ticket: Ticket) -> bool:
        reported = first_report.get(ticket.id)
        return (
            ticket.status == TicketStatus.OVERDUE
            or ticket.became_overdue_at is not None
            or (reported is not None and reported > ticket.deadline)
        )

    response_hours = [
        (first_report[t.id] - t.created_at).total_seconds() / 3600 for t in tickets if t.id in first_report
    ]
    avg_response = sum(response_hours) / len(response_hours) if response_hours else None

    closes_by_place: dict[tuple[uuid.UUID, str], int] = {}
    for ticket, site_id, endpoint in rows:
        if ticket.status == TicketStatus.VERIFIED_CLOSED:
            closes_by_place[(site_id, endpoint)] = closes_by_place.get((site_id, endpoint), 0) + 1
    repeats = sum(count - 1 for count in closes_by_place.values())

    return VendorScorecardRead(
        vendor_id=vendor.id,
        vendor_name=vendor.name,
        fix_rate=round(fix_rate, 4),
        avg_response_time_hours=round(avg_response, 2) if avg_response is not None else None,
        missed_deadlines=sum(1 for t in tickets if missed(t)),
        repeat_vulnerabilities=repeats,
        verified_ticket_count=len(closed),
        overdue_ticket_count=len(overdue_now),
        total_ticket_count=len(tickets),
    )