"""Alerts to a vendor when a ticket is assigned to them or its deadline
changes (SRS 4.3-4: the Vendor is notified through the alert system)."""
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.models.alert import Alert
from app.models.enums import AlertDeliveryStatus, AlertLevel, AlertTriggerType, FindingStatus
from tests import factories
from tests.factories import bearer
from tests.lifecycle.helpers import API, XSS_ENDPOINT, XSS_TITLE, alerts_for

NOTIFY = "app.tasks.notification_tasks.notify_vendor_of_ticket_change"


def assign(client, admin, ticket, **body):
    return client.post(f"{API}/tickets/{ticket.id}/assign", headers=bearer(admin), json=body)


def notify(ticket, kind):
    from app.tasks.notification_tasks import notify_vendor_of_ticket_change

    notify_vendor_of_ticket_change(str(ticket.id), kind)


def deadline_text(ticket):
    return ticket.deadline.astimezone(timezone.utc).strftime("%d %b %Y, %H:%M UTC")


def in_days(days):
    return (datetime.now(timezone.utc) + timedelta(days=days)).isoformat()


@pytest.fixture()
def unassigned_ticket(db, dept):
    site = factories.make_site(db, dept, vendor=None, name="No vendor site")
    finding = factories.make_finding(db, site, status=FindingStatus.APPROVED)
    return factories.make_ticket(db, finding, None)


# ---- What the API queues ----

def test_assigning_a_vendor_queues_one_assigned_alert(client, admin, vendor_a, unassigned_ticket, task_calls):
    response = assign(client, admin, unassigned_ticket, vendor_id=str(vendor_a.id))

    assert response.status_code == 200
    assert task_calls == [(NOTIFY, (str(unassigned_ticket.id), "assigned"))]


def test_assigning_with_a_new_deadline_still_queues_a_single_alert(client, admin, vendor_a, unassigned_ticket, task_calls):
    response = assign(
        client, admin, unassigned_ticket,
        vendor_id=str(vendor_a.id), deadline_override=in_days(20), override_reason="Release window.",
    )

    assert response.status_code == 200
    assert task_calls == [(NOTIFY, (str(unassigned_ticket.id), "assigned"))]


def test_moving_a_ticket_to_another_vendor_alerts_the_new_vendor(client, admin, vendor_b, open_ticket, task_calls):
    response = assign(client, admin, open_ticket, vendor_id=str(vendor_b.id))

    assert response.status_code == 200
    assert task_calls == [(NOTIFY, (str(open_ticket.id), "assigned"))]


def test_changing_only_the_deadline_queues_a_deadline_alert(client, admin, open_ticket, task_calls):
    response = assign(client, admin, open_ticket, deadline_override=in_days(20), override_reason="Release window.")

    assert response.status_code == 200
    assert task_calls == [(NOTIFY, (str(open_ticket.id), "deadline_changed"))]


def test_a_save_that_changes_nothing_sends_no_alert(client, admin, vendor_a, open_ticket, task_calls):
    response = assign(client, admin, open_ticket, vendor_id=str(vendor_a.id))

    assert response.status_code == 200
    assert task_calls == []


def test_setting_the_deadline_it_already_has_sends_no_alert(client, admin, open_ticket, task_calls):
    response = assign(
        client, admin, open_ticket,
        deadline_override=open_ticket.deadline.isoformat(), override_reason="Confirmed with the vendor.",
    )

    assert response.status_code == 200
    assert task_calls == []


def test_a_refused_assignment_sends_no_alert(client, admin, unassigned_ticket, task_calls):
    assert assign(client, admin, unassigned_ticket).status_code == 400  # no vendor named or mapped
    assert task_calls == []


def test_a_deadline_without_a_time_zone_is_read_as_utc(client, db, admin, open_ticket):
    response = assign(client, admin, open_ticket, deadline_override="2030-01-15T12:00:00", override_reason="Release window.")

    assert response.status_code == 200
    db.refresh(open_ticket)
    assert open_ticket.deadline == datetime(2030, 1, 15, 12, 0, tzinfo=timezone.utc)


# ---- What the task sends ----

def test_the_assigned_alert_goes_to_the_vendors_login_and_names_the_deadline(
    db, admin, vendor_a_user, vendor_b_user, open_ticket
):
    notify(open_ticket, "assigned")

    alerts = alerts_for(db, vendor_a_user, AlertTriggerType.TICKET_ASSIGNED)
    assert len(alerts) == 1
    alert = alerts[0]
    assert alert.level == AlertLevel.WARNING
    assert alert.ticket_id == open_ticket.id
    assert alert.delivery_status == AlertDeliveryStatus.DELIVERED
    assert alert.message == (
        f"Ticket Assigned (High severity) on Juice Shop. Fix it by {deadline_text(open_ticket)}. "
        "Open the ticket in SentinelX for details."
    )
    assert XSS_TITLE not in alert.message
    assert XSS_ENDPOINT not in alert.message
    assert alerts_for(db, vendor_b_user) == []
    assert alerts_for(db, admin) == []


def test_the_deadline_alert_gives_the_new_deadline(db, vendor_a_user, open_ticket):
    notify(open_ticket, "deadline_changed")

    alert = alerts_for(db, vendor_a_user, AlertTriggerType.TICKET_DEADLINE_CHANGED)[0]
    assert alert.message == (
        f"Ticket Deadline Changed (High severity) on Juice Shop. The new deadline is {deadline_text(open_ticket)}."
    )


def test_every_active_login_at_the_vendor_is_alerted_and_deactivated_ones_are_not(
    db, vendor_a, vendor_a_user, open_ticket
):
    second = factories.make_vendor_user(db, vendor_a)
    deactivated = factories.make_vendor_user(db, vendor_a, is_active=False)

    notify(open_ticket, "assigned")

    assert len(alerts_for(db, vendor_a_user)) == 1
    assert len(alerts_for(db, second)) == 1
    assert alerts_for(db, deactivated) == []


def test_two_tickets_assigned_in_a_row_each_get_an_alert(db, vendor_a, vendor_a_user, site, open_ticket):
    second_finding = factories.make_finding(db, site, status=FindingStatus.APPROVED, endpoint="/second")
    second = factories.make_ticket(db, second_finding, vendor_a)

    notify(open_ticket, "assigned")
    notify(second, "assigned")

    alerts = alerts_for(db, vendor_a_user, AlertTriggerType.TICKET_ASSIGNED)
    assert {alert.ticket_id for alert in alerts} == {open_ticket.id, second.id}


def test_a_muted_kind_is_logged_but_not_sent(db, vendor_a_user, open_ticket):
    vendor_a_user.muted_trigger_types = ["ticket_assigned"]
    db.flush()

    notify(open_ticket, "assigned")

    alert = alerts_for(db, vendor_a_user, AlertTriggerType.TICKET_ASSIGNED)[0]
    assert alert.delivery_status == AlertDeliveryStatus.SUPPRESSED


def test_a_vendor_with_no_login_causes_no_alert_and_no_error(db, vendor_b, site):
    finding = factories.make_finding(db, site, status=FindingStatus.APPROVED, endpoint="/b")
    ticket = factories.make_ticket(db, finding, vendor_b)

    notify(ticket, "assigned")

    assert db.execute(select(Alert)).scalars().all() == []


def test_a_ticket_without_a_vendor_sends_nothing(db, unassigned_ticket):
    notify(unassigned_ticket, "assigned")

    assert db.execute(select(Alert)).scalars().all() == []


def test_an_unknown_kind_fails_loudly(open_ticket):
    with pytest.raises(KeyError):
        notify(open_ticket, "something_else")


@pytest.mark.parametrize("kind", ["ticket_assigned", "ticket_deadline_changed"])
def test_a_vendor_can_mute_the_new_kinds(client, vendor_a_user, kind):
    response = client.patch(
        f"{API}/users/me/preferences", headers=bearer(vendor_a_user), json={"muted_trigger_types": [kind]}
    )

    assert response.status_code == 200
    assert response.json()["muted_trigger_types"] == [kind]