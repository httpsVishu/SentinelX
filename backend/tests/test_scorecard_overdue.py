"""Missed deadlines on the scorecard after the overdue marker was added."""
from datetime import datetime, timedelta, timezone
from itertools import count

import pytest

from app.models.enums import FindingStatus, TicketStatus
from app.models.ticket import RemediationSubmission
from app.services.scorecard_service import compute_vendor_scorecard
from tests import factories
from tests.factories import bearer
from tests.lifecycle.helpers import API, XSS_ENDPOINT, XSS_TITLE

NOW = datetime.now(timezone.utc)
_endpoints = count(1)


def add_ticket(db, site, vendor, status, *, deadline=None, became_overdue_at=None, created_at=None):
    finding = factories.make_finding(db, site, status=FindingStatus.APPROVED, endpoint=f"/e{next(_endpoints)}")
    ticket = factories.make_ticket(db, finding, vendor, status=status, deadline=deadline, created_at=created_at)
    ticket.became_overdue_at = became_overdue_at
    db.flush()
    return ticket


def report(db, ticket, user, at):
    db.add(RemediationSubmission(ticket_id=ticket.id, vendor_user_id=user.id, note="Fixed it.", submitted_at=at))
    db.flush()


@pytest.fixture()
def site(db, dept, vendor_a):
    return factories.make_site(db, dept, vendor=vendor_a, url="http://juice-shop.local:3000")


def missed(db, vendor):
    return compute_vendor_scorecard(db, vendor.id).missed_deadlines


def test_a_ticket_that_was_overdue_and_then_reopened_still_counts(db, site, vendor_a):
    add_ticket(db, site, vendor_a, TicketStatus.FIX_FAILED_REOPENED, became_overdue_at=NOW - timedelta(days=2))

    assert missed(db, vendor_a) == 1


def test_a_ticket_that_was_overdue_and_then_closed_counts_once(db, site, vendor_a, vendor_a_user):
    ticket = add_ticket(
        db, site, vendor_a, TicketStatus.VERIFIED_CLOSED,
        deadline=NOW - timedelta(days=4), became_overdue_at=NOW - timedelta(days=3),
        created_at=NOW - timedelta(days=10),
    )
    report(db, ticket, vendor_a_user, NOW - timedelta(days=2))  # late as well: still one miss, not two

    assert missed(db, vendor_a) == 1


def test_a_ticket_fixed_on_time_is_not_a_miss(db, site, vendor_a, vendor_a_user):
    ticket = add_ticket(
        db, site, vendor_a, TicketStatus.VERIFIED_CLOSED,
        deadline=NOW - timedelta(days=1), created_at=NOW - timedelta(days=9),
    )
    report(db, ticket, vendor_a_user, NOW - timedelta(days=3))

    assert missed(db, vendor_a) == 0


def test_a_ticket_still_open_before_its_deadline_is_not_a_miss(db, site, vendor_a):
    add_ticket(db, site, vendor_a, TicketStatus.OPEN, deadline=NOW + timedelta(days=3))

    assert missed(db, vendor_a) == 0


def test_the_daily_check_records_the_miss_and_it_survives_a_late_fix(client, db, site, vendor_a, vendor_a_user):
    from app.tasks.deadline_tasks import check_overdue_tickets

    finding = factories.make_finding(
        db, site, status=FindingStatus.APPROVED, endpoint=XSS_ENDPOINT, title=XSS_TITLE
    )
    ticket = factories.make_ticket(
        db, finding, vendor_a, deadline=NOW - timedelta(days=1), created_at=NOW - timedelta(days=8)
    )

    check_overdue_tickets()
    db.refresh(ticket)
    assert ticket.status == TicketStatus.OVERDUE
    assert ticket.became_overdue_at is not None

    # The vendor fixes it late and the re-scan passes.
    fix = client.post(
        f"{API}/tickets/mine/{ticket.id}/remediate", headers=bearer(vendor_a_user), json={"note": "Fixed it."}
    )
    assert fix.status_code == 200
    from app.tasks.verification_tasks import run_verification_scan

    run_verification_scan(str(ticket.id))

    db.refresh(ticket)
    card = compute_vendor_scorecard(db, vendor_a.id)
    assert ticket.status == TicketStatus.VERIFIED_CLOSED
    assert (card.verified_ticket_count, card.overdue_ticket_count, card.missed_deadlines) == (1, 0, 1)
    assert card.fix_rate == 1.0


def test_marking_a_ticket_overdue_keeps_the_first_time(db, site, vendor_a):
    from app.services import ticket_service

    first = NOW - timedelta(days=5)
    ticket = add_ticket(db, site, vendor_a, TicketStatus.OPEN, deadline=NOW - timedelta(days=1), became_overdue_at=first)

    assert ticket_service.mark_overdue_if_past_deadline(db, ticket) is True

    assert ticket.became_overdue_at == first