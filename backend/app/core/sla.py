"""SLA / deadline calculation logic.

Centralizes the severity -> deadline formula so it's defined in exactly one
place, per SRS 4.5-3: "The deadline formula shall be configurable by the
Admin department-wide, rather than fixed per site."

get_active_sla_config() resolves the currently-effective SLAConfig row for a
department (the most recent one whose effective_from is not in the future).
calculate_deadline() then uses it to produce a concrete datetime, called
once at ticket-creation time by app/services/ticket_service.py — the result
is stored on the Ticket and never recalculated later.
"""
from datetime import datetime, timedelta, timezone
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.enums import Severity
from app.models.sla_config import SLAConfig


def get_active_sla_config(db: Session, department_id: uuid.UUID) -> SLAConfig:
    """Return the SLAConfig row currently in effect for a department.

    Raises ValueError if no SLA configuration has ever been seeded for the
    department — this should never happen past initial seed/setup, and is
    treated as a setup error rather than silently falling back to hardcoded
    defaults, so misconfiguration is loud rather than silent.
    """
    now = datetime.now(timezone.utc)
    stmt = (
        select(SLAConfig)
        .where(SLAConfig.department_id == department_id, SLAConfig.effective_from <= now)
        .order_by(SLAConfig.effective_from.desc())
        .limit(1)
    )
    config = db.execute(stmt).scalar_one_or_none()
    if config is None:
        raise ValueError(
            f"No active SLA configuration found for department {department_id}. "
            "Seed an initial SLAConfig before creating tickets."
        )
    return config


def days_for_severity(config: SLAConfig, severity: Severity) -> int:
    mapping = {
        Severity.CRITICAL: config.critical_days,
        Severity.HIGH: config.high_days,
        Severity.MEDIUM: config.medium_days,
        Severity.LOW: config.low_days,
    }
    if severity not in mapping:
        # Informational findings never reach ticket creation (SRS: only
        # findings above Informational severity go to Admin review), so
        # this should be unreachable in practice — fail loudly if it isn't.
        raise ValueError(f"No SLA deadline is defined for severity {severity}")
    return mapping[severity]


def calculate_deadline(
    db: Session, department_id: uuid.UUID, severity: Severity, from_time: datetime | None = None
) -> tuple[datetime, SLAConfig]:
    """Calculate the suggested deadline for a new ticket.

    Returns (deadline, config_used) so the caller (ticket_service.py) can
    store both the resolved deadline and, if desired, reference which
    SLAConfig version produced it.
    """
    config = get_active_sla_config(db, department_id)
    days = days_for_severity(config, severity)
    base_time = from_time or datetime.now(timezone.utc)
    return base_time + timedelta(days=days), config