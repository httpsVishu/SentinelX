"""Alert creation, delivery, grouping, muting and the alert log."""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from sqlalchemy import select

from app.models.alert import Alert
from app.models.enums import AlertDeliveryStatus, AlertLevel, AlertTriggerType, AuditAction
from app.notifications.base import NotificationAdapter, NotificationDeliveryError
from app.services.alert_service import create_and_dispatch_alert
from tests import factories
from tests.factories import bearer
from tests.lifecycle.helpers import audit_actions

API = "/api/v1"


class RecordingAdapter(NotificationAdapter):
    name = "recording"

    def __init__(self, error: Exception | None = None):
        self.sent: list[tuple[str, str, str]] = []
        self.error = error

    def send(self, recipient_email, subject, message):
        if self.error is not None:
            raise self.error
        self.sent.append((recipient_email, subject, message))


@pytest.fixture()
def adapter(monkeypatch):
    recording = RecordingAdapter()
    monkeypatch.setattr("app.services.alert_service.get_notification_adapter", lambda: recording)
    return recording


@pytest.fixture()
def site(db, dept, vendor_a):
    return factories.make_site(db, dept, vendor=vendor_a, name="Juice Shop")


def raise_alert(db, user, site=None, trigger=AlertTriggerType.DEADLINE_MISSED):
    return create_and_dispatch_alert(
        db,
        user,
        trigger,
        site_name=site.name if site else "Juice Shop",
        action_required="Review the ticket.",
        severity="high",
        site_id=site.id if site else None,
    )


def alert_count(db, user):
    return len(db.execute(select(Alert).where(Alert.recipient_user_id == user.id)).scalars().all())


# ---- Creating and sending ----

def test_an_alert_is_a_short_plain_message_sent_to_the_recipient(db, admin, site, adapter):
    alert = raise_alert(db, admin, site)

    assert alert.message == "Deadline Missed (High severity) on Juice Shop. Review the ticket."
    assert adapter.sent == [(admin.email, "SentinelX: deadline_missed", alert.message)]
    assert alert.delivery_status == AlertDeliveryStatus.DELIVERED
    assert alert.delivered_at is not None
    assert AuditAction.ALERT_DELIVERED in audit_actions(db, alert.id)


@pytest.mark.parametrize(
    "trigger,level",
    [
        (AlertTriggerType.CRITICAL_FINDING_CONFIRMED, AlertLevel.URGENT),
        (AlertTriggerType.UNAUTHORIZED_CHANGE, AlertLevel.URGENT),
        (AlertTriggerType.DEADLINE_MISSED, AlertLevel.URGENT),
        (AlertTriggerType.VERIFICATION_FAILED, AlertLevel.URGENT),
        (AlertTriggerType.HIGH_FINDING_CONFIRMED, AlertLevel.WARNING),
        (AlertTriggerType.SCAN_FAILED, AlertLevel.WARNING),
        (AlertTriggerType.PIPELINE_FAILURE, AlertLevel.WARNING),
    ],
)
def test_each_kind_of_alert_has_its_level(db, admin, site, adapter, trigger, level):
    assert raise_alert(db, admin, site, trigger).level == level


@pytest.mark.parametrize(
    "error",
    [NotificationDeliveryError("gateway is down"), RuntimeError("gateway is down")],
    ids=["gateway error", "unexpected error"],
)
def test_a_delivery_failure_is_logged_and_the_alert_is_kept(db, admin, site, monkeypatch, error):
    monkeypatch.setattr("app.services.alert_service.get_notification_adapter", lambda: RecordingAdapter(error))

    alert = raise_alert(db, admin, site)

    assert alert is not None
    saved = db.execute(select(Alert).where(Alert.id == alert.id)).scalar_one()
    assert saved.delivery_status == AlertDeliveryStatus.FAILED
    assert saved.delivery_error == "gateway is down"
    assert saved.delivered_at is None
    assert AuditAction.ALERT_DELIVERY_FAILED in audit_actions(db, alert.id)


# ---- Muting ----

def test_a_muted_kind_is_logged_but_not_sent(db, admin, site, adapter):
    admin.muted_trigger_types = ["deadline_missed"]
    db.flush()

    muted = raise_alert(db, admin, site)
    other = raise_alert(db, admin, site, AlertTriggerType.SCAN_FAILED)

    assert muted.delivery_status == AlertDeliveryStatus.SUPPRESSED
    assert other.delivery_status == AlertDeliveryStatus.DELIVERED
    assert [sent[1] for sent in adapter.sent] == ["SentinelX: scan_failed"]


def test_muting_through_the_api_hides_the_delivery_not_the_alert(client, db, admin, site, adapter):
    saved = client.patch(
        f"{API}/users/me/preferences", headers=bearer(admin), json={"muted_trigger_types": ["scan_failed"]}
    )
    assert saved.status_code == 200
    assert saved.json()["muted_trigger_types"] == ["scan_failed"]
    db.refresh(admin)

    alert = raise_alert(db, admin, site, AlertTriggerType.SCAN_FAILED)

    assert alert.delivery_status == AlertDeliveryStatus.SUPPRESSED
    assert adapter.sent == []
    listed = client.get(f"{API}/alerts", headers=bearer(admin)).json()
    assert [a["id"] for a in listed] == [str(alert.id)]
    assert listed[0]["delivery_status"] == "suppressed"


def test_mute_choices_must_be_real_alert_kinds_and_are_stored_without_duplicates(client, admin):
    rejected = client.patch(
        f"{API}/users/me/preferences", headers=bearer(admin), json={"muted_trigger_types": ["not_a_real_alert"]}
    )
    too_long = client.patch(
        f"{API}/users/me/preferences", headers=bearer(admin), json={"muted_trigger_types": ["x" * 500]}
    )
    accepted = client.patch(
        f"{API}/users/me/preferences",
        headers=bearer(admin),
        json={"muted_trigger_types": ["scan_failed", "deadline_missed", "scan_failed"]},
    )

    assert rejected.status_code == 422
    assert too_long.status_code == 422
    assert accepted.status_code == 200
    assert accepted.json()["muted_trigger_types"] == ["deadline_missed", "scan_failed"]


# ---- Grouping ----

def test_repeat_alerts_for_the_same_site_within_five_minutes_are_grouped(db, admin, site, adapter):
    first = raise_alert(db, admin, site)
    second = raise_alert(db, admin, site)

    assert first is not None
    assert second is None
    assert len(adapter.sent) == 1
    assert alert_count(db, admin) == 1


def test_grouping_applies_only_to_the_same_kind_site_and_recipient(db, dept, vendor_b, admin, site, adapter):
    other_site = factories.make_site(db, dept, vendor=vendor_b, name="Other site")
    second_admin = factories.make_admin(db, dept)

    raise_alert(db, admin, site)

    assert raise_alert(db, admin, other_site) is not None
    assert raise_alert(db, admin, site, AlertTriggerType.SCAN_FAILED) is not None
    assert raise_alert(db, second_admin, site) is not None


def test_an_alert_older_than_five_minutes_does_not_group(db, admin, site, adapter):
    earlier = raise_alert(db, admin, site)
    earlier.created_at = datetime.now(timezone.utc) - timedelta(minutes=10)
    db.flush()

    assert raise_alert(db, admin, site) is not None


def test_alerts_without_a_site_are_never_grouped(db, admin, adapter):
    assert raise_alert(db, admin, None) is not None
    assert raise_alert(db, admin, None) is not None


# ---- The alert log ----

@pytest.fixture()
def alert_world(db, dept, admin, vendor_a_user, site):
    other_site = factories.make_site(db, dept, name="Other site")
    colleague = factories.make_admin(db, dept)
    outsider = factories.make_admin(db, factories.make_department(db))
    return SimpleNamespace(
        deadline=factories.make_alert(db, admin, site=site, trigger=AlertTriggerType.DEADLINE_MISSED, level=AlertLevel.URGENT),
        scan_failed=factories.make_alert(db, admin, site=other_site, trigger=AlertTriggerType.SCAN_FAILED, level=AlertLevel.WARNING),
        colleague=factories.make_alert(db, colleague, site=site, trigger=AlertTriggerType.HIGH_FINDING_CONFIRMED, level=AlertLevel.WARNING),
        vendor=factories.make_alert(db, vendor_a_user, site=site, trigger=AlertTriggerType.DEADLINE_MISSED, level=AlertLevel.URGENT),
        outsider=factories.make_alert(db, outsider, trigger=AlertTriggerType.SCAN_FAILED, level=AlertLevel.WARNING),
    )


def ids(response):
    return {item["id"] for item in response.json()}


def test_the_admin_log_covers_every_admin_in_the_department_and_nobody_else(client, admin, alert_world):
    response = client.get(f"{API}/alerts", headers=bearer(admin))

    w = alert_world
    assert ids(response) == {str(w.deadline.id), str(w.scan_failed.id), str(w.colleague.id)}


@pytest.mark.parametrize(
    "query,expected",
    [
        ("level=urgent", {"deadline"}),
        ("level=warning", {"scan_failed", "colleague"}),
        ("trigger_type=scan_failed", {"scan_failed"}),
    ],
)
def test_the_admin_log_can_be_filtered(client, admin, alert_world, query, expected):
    response = client.get(f"{API}/alerts?{query}", headers=bearer(admin))

    assert ids(response) == {str(getattr(alert_world, name).id) for name in expected}


def test_the_admin_log_can_be_filtered_by_site(client, admin, site, alert_world):
    response = client.get(f"{API}/alerts?site_id={site.id}", headers=bearer(admin))

    assert ids(response) == {str(alert_world.deadline.id), str(alert_world.colleague.id)}


def test_an_unknown_filter_value_is_rejected(client, admin):
    assert client.get(f"{API}/alerts?level=bogus", headers=bearer(admin)).status_code == 422


def test_a_vendor_sees_only_their_own_alerts(client, vendor_a_user, alert_world):
    everything = client.get(f"{API}/alerts/mine", headers=bearer(vendor_a_user))
    urgent = client.get(f"{API}/alerts/mine?level=urgent", headers=bearer(vendor_a_user))
    warnings = client.get(f"{API}/alerts/mine?level=warning", headers=bearer(vendor_a_user))

    assert ids(everything) == {str(alert_world.vendor.id)}
    assert ids(urgent) == {str(alert_world.vendor.id)}
    assert ids(warnings) == set()


def test_the_delivery_error_is_for_admins_only(client, db, admin, vendor_a_user, site):
    error = "smtp.internal.example refused the connection"
    for recipient in (admin, vendor_a_user):
        alert = factories.make_alert(db, recipient, site=site)
        alert.delivery_status = AlertDeliveryStatus.FAILED
        alert.delivery_error = error
    db.flush()

    vendor_view = client.get(f"{API}/alerts/mine", headers=bearer(vendor_a_user))
    admin_view = client.get(f"{API}/alerts", headers=bearer(admin))

    assert vendor_view.json()[0]["delivery_error"] is None
    assert "smtp.internal" not in vendor_view.text
    assert admin_view.json()[0]["delivery_error"] == error