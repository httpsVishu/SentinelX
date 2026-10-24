"""Vendor scorecard: worked out from ticket history and never edited."""
from datetime import datetime, timedelta, timezone
from itertools import count

import pytest

from app.models.enums import FindingStatus, TicketStatus
from app.models.ticket import RemediationSubmission
from app.services.scorecard_service import compute_vendor_scorecard
from tests import factories
from tests.factories import bearer

API = "/api/v1"
NOW = datetime.now(timezone.utc)
_endpoints = count(1)


# Timestamps are set by hand everywhere. A database default is the start of
# the test transaction, so every default would be the same instant.

def add_ticket(db, site, vendor, status, *, endpoint=None, deadline=None, created_at=None, closed_at=None):
    finding = factories.make_finding(
        db, site, status=FindingStatus.APPROVED, endpoint=endpoint or f"/e{next(_endpoints)}"
    )
    ticket = factories.make_ticket(db, finding, vendor, status=status, deadline=deadline, created_at=created_at)
    if closed_at is not None:
        ticket.closed_at = closed_at
        db.flush()
    return ticket


def add_report(db, ticket, user, at):
    db.add(RemediationSubmission(ticket_id=ticket.id, vendor_user_id=user.id, note="Fixed it.", submitted_at=at))
    db.flush()


@pytest.fixture()
def site(db, dept, vendor_a):
    return factories.make_site(db, dept, vendor=vendor_a, name="Juice Shop")


def test_a_vendor_with_no_tickets_has_an_empty_scorecard(db, vendor_a):
    card = compute_vendor_scorecard(db, vendor_a.id)

    assert card.vendor_name == "Vendor A"
    assert card.fix_rate == 0.0
    assert card.avg_response_time_hours is None
    assert (
        card.missed_deadlines,
        card.repeat_vulnerabilities,
        card.verified_ticket_count,
        card.overdue_ticket_count,
        card.total_ticket_count,
    ) == (0, 0, 0, 0, 0)


def test_fix_rate_is_verified_fixes_out_of_tickets_that_ended_closed_overdue_or_reopened(db, site, vendor_a):
    for _ in range(3):
        add_ticket(db, site, vendor_a, TicketStatus.VERIFIED_CLOSED)
    add_ticket(db, site, vendor_a, TicketStatus.OVERDUE)
    add_ticket(db, site, vendor_a, TicketStatus.OPEN)  # still in progress: counts for neither side
    add_ticket(db, site, vendor_a, TicketStatus.FIX_SUBMITTED_PENDING_VERIFICATION)

    card = compute_vendor_scorecard(db, vendor_a.id)

    assert card.fix_rate == 0.75
    assert card.verified_ticket_count == 3
    assert card.overdue_ticket_count == 1
    assert card.total_ticket_count == 6
    assert card.repeat_vulnerabilities == 0


def test_a_reopened_ticket_counts_against_the_fix_rate(db, site, vendor_a):
    add_ticket(db, site, vendor_a, TicketStatus.VERIFIED_CLOSED)
    add_ticket(db, site, vendor_a, TicketStatus.FIX_FAILED_REOPENED)

    assert compute_vendor_scorecard(db, vendor_a.id).fix_rate == 0.5


def test_a_reported_fix_that_is_not_verified_counts_for_nothing(db, site, vendor_a, vendor_a_user):
    ticket = add_ticket(db, site, vendor_a, TicketStatus.FIX_SUBMITTED_PENDING_VERIFICATION)
    add_report(db, ticket, vendor_a_user, NOW)

    card = compute_vendor_scorecard(db, vendor_a.id)

    assert card.verified_ticket_count == 0
    assert card.fix_rate == 0.0


def test_missed_deadlines_include_overdue_tickets_and_late_fixes(db, site, vendor_a, vendor_a_user):
    add_ticket(db, site, vendor_a, TicketStatus.OVERDUE, deadline=NOW - timedelta(days=2))

    on_time = add_ticket(
        db, site, vendor_a, TicketStatus.VERIFIED_CLOSED, created_at=NOW - timedelta(days=5), deadline=NOW - timedelta(days=1)
    )
    add_report(db, on_time, vendor_a_user, NOW - timedelta(days=2))

    late = add_ticket(
        db, site, vendor_a, TicketStatus.VERIFIED_CLOSED, created_at=NOW - timedelta(days=9), deadline=NOW - timedelta(days=4)
    )
    add_report(db, late, vendor_a_user, NOW - timedelta(days=3))

    assert compute_vendor_scorecard(db, vendor_a.id).missed_deadlines == 2  # the overdue one and the late fix


def test_average_response_time_uses_each_tickets_first_report(db, site, vendor_a, vendor_a_user):
    start = NOW - timedelta(days=3)

    first = add_ticket(db, site, vendor_a, TicketStatus.VERIFIED_CLOSED, created_at=start, deadline=NOW)
    add_report(db, first, vendor_a_user, start + timedelta(hours=2))
    add_report(db, first, vendor_a_user, start + timedelta(hours=30))  # a later report must not change it

    second = add_ticket(db, site, vendor_a, TicketStatus.VERIFIED_CLOSED, created_at=start, deadline=NOW)
    add_report(db, second, vendor_a_user, start + timedelta(hours=4))

    add_ticket(db, site, vendor_a, TicketStatus.OPEN, created_at=start)  # no report yet, so not in the average

    assert compute_vendor_scorecard(db, vendor_a.id).avg_response_time_hours == 3.0


def test_repeat_vulnerabilities_count_the_same_endpoint_breaking_again(db, dept, site, vendor_a):
    other_site = factories.make_site(db, dept, vendor=vendor_a, name="Other site")

    add_ticket(db, site, vendor_a, TicketStatus.VERIFIED_CLOSED, endpoint="/login")
    add_ticket(db, site, vendor_a, TicketStatus.VERIFIED_CLOSED, endpoint="/login")  # same endpoint again: one repeat
    add_ticket(db, site, vendor_a, TicketStatus.VERIFIED_CLOSED, endpoint="/search")  # different endpoint
    add_ticket(db, other_site, vendor_a, TicketStatus.VERIFIED_CLOSED, endpoint="/login")  # different site

    assert compute_vendor_scorecard(db, vendor_a.id).repeat_vulnerabilities == 1


def test_another_vendors_tickets_do_not_count(db, site, vendor_a, vendor_b):
    add_ticket(db, site, vendor_a, TicketStatus.VERIFIED_CLOSED)
    add_ticket(db, site, vendor_b, TicketStatus.OVERDUE)

    card_a = compute_vendor_scorecard(db, vendor_a.id)
    card_b = compute_vendor_scorecard(db, vendor_b.id)

    assert (card_a.total_ticket_count, card_a.fix_rate, card_a.overdue_ticket_count) == (1, 1.0, 0)
    assert (card_b.total_ticket_count, card_b.fix_rate, card_b.overdue_ticket_count) == (1, 0.0, 1)


def test_admin_and_vendor_read_the_same_numbers(client, db, admin, site, vendor_a, vendor_a_user):
    add_ticket(db, site, vendor_a, TicketStatus.VERIFIED_CLOSED)
    add_ticket(db, site, vendor_a, TicketStatus.VERIFIED_CLOSED)

    as_admin = client.get(f"{API}/scorecards/{vendor_a.id}", headers=bearer(admin))
    as_vendor = client.get(f"{API}/scorecards/mine", headers=bearer(vendor_a_user))

    assert as_admin.status_code == 200
    assert as_vendor.status_code == 200
    assert as_admin.json() == as_vendor.json()
    assert as_admin.json()["fix_rate"] == 1.0
    assert as_admin.json()["verified_ticket_count"] == 2


@pytest.mark.parametrize("method", ["POST", "PUT", "PATCH", "DELETE"])
@pytest.mark.parametrize("path", ["/scorecards/mine", "/scorecards/{vendor}"])
def test_scorecards_cannot_be_written_by_anyone(client, admin, vendor_a, method, path):
    url = API + path.replace("{vendor}", str(vendor_a.id))
    kwargs = {"json": {"fix_rate": 1.0}} if method != "DELETE" else {}

    response = client.request(method, url, headers=bearer(admin), **kwargs)

    assert response.status_code == 405