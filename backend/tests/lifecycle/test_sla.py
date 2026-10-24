"""Deadline calculation and the department SLA settings."""
from datetime import datetime, timedelta, timezone

import pytest

from app.core.sla import calculate_deadline
from app.models.enums import Severity
from app.models.sla_config import SLAConfig
from app.services import ticket_service
from tests.factories import bearer, make_department, make_finding, make_site, make_vendor
from tests.lifecycle.helpers import API

NOW = datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc)


@pytest.mark.parametrize(
    "severity,days",
    [(Severity.CRITICAL, 3), (Severity.HIGH, 7), (Severity.MEDIUM, 15), (Severity.LOW, 30)],
)
def test_default_deadlines_follow_severity(db, dept, severity, days):
    deadline, _config = calculate_deadline(db, dept.id, severity, from_time=NOW)

    assert deadline == NOW + timedelta(days=days)


def test_informational_findings_have_no_deadline(db, dept):
    with pytest.raises(ValueError):
        calculate_deadline(db, dept.id, Severity.INFORMATIONAL)


def test_a_department_without_settings_fails_loudly(db):
    department = make_department(db, with_sla=False)

    with pytest.raises(ValueError, match="No active SLA"):
        calculate_deadline(db, department.id, Severity.HIGH)


def test_the_newest_settings_in_effect_win_and_future_ones_wait(db, dept):
    now = datetime.now(timezone.utc)
    db.add_all(
        [
            SLAConfig(department_id=dept.id, critical_days=1, high_days=2, medium_days=4, low_days=8,
                      effective_from=now - timedelta(seconds=5)),
            SLAConfig(department_id=dept.id, critical_days=9, high_days=9, medium_days=9, low_days=9,
                      effective_from=now + timedelta(days=1)),
        ]
    )
    db.flush()

    deadline, config = calculate_deadline(db, dept.id, Severity.HIGH, from_time=NOW)

    assert config.high_days == 2
    assert deadline == NOW + timedelta(days=2)


def test_sla_endpoints_show_and_save_settings(client, admin):
    shown = client.get(f"{API}/schedules/sla", headers=bearer(admin))
    assert shown.status_code == 200
    assert shown.json()["critical_days"] == 3
    assert "effective_from" in shown.json()

    saved = client.put(
        f"{API}/schedules/sla",
        headers=bearer(admin),
        json={"critical_days": 1, "high_days": 2, "medium_days": 3, "low_days": 4},
    )
    assert saved.status_code == 200

    assert client.get(f"{API}/schedules/sla", headers=bearer(admin)).json()["critical_days"] == 1


@pytest.mark.parametrize("bad_value", [0, -1, 366])
def test_sla_settings_must_be_a_sensible_number_of_days(client, admin, bad_value):
    response = client.put(
        f"{API}/schedules/sla",
        headers=bearer(admin),
        json={"critical_days": bad_value, "high_days": 7, "medium_days": 15, "low_days": 30},
    )

    assert response.status_code == 422


def test_changing_the_settings_does_not_move_existing_deadlines(client, db, dept, admin):
    vendor = make_vendor(db, dept)
    site = make_site(db, dept, vendor=vendor)
    first = ticket_service.create_ticket_from_approved_finding(db, make_finding(db, site), dept.id)
    original_deadline = first.deadline

    client.put(
        f"{API}/schedules/sla",
        headers=bearer(admin),
        json={"critical_days": 1, "high_days": 2, "medium_days": 3, "low_days": 4},
    )
    second = ticket_service.create_ticket_from_approved_finding(db, make_finding(db, site, endpoint="/other"), dept.id)

    db.refresh(first)
    assert first.deadline == original_deadline  # kept the 7 days it was given
    expected = datetime.now(timezone.utc) + timedelta(days=2)
    assert abs((second.deadline - expected).total_seconds()) < 120  # new tickets use the new settings