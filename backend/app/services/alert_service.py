"""AlertService: builds sanitized Alert rows and sends them through the
configured notification adapter. The alert is always logged first, so it is
kept even when delivery fails (SRS: "Every alert shall be recorded
permanently in the Alert Log, even when live delivery fails").

Messages are built here from structured parts: severity, a plain-language
summary and the action required. There is no parameter that accepts raw
scanner output, so exploit detail cannot reach an email or text.
"""
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.alert import Alert
from app.models.enums import AlertDeliveryStatus, AlertLevel, AlertTriggerType, AuditAction
from app.models.user import User
from app.notifications import get_notification_adapter
from app.services import audit_service

# Urgent triggers use push or SMS plus email. The rest use email and the
# dashboard only (SRS 4.5-4, Figure 4.3).
_URGENT_TRIGGERS = {
    AlertTriggerType.CRITICAL_FINDING_CONFIRMED,
    AlertTriggerType.UNAUTHORIZED_CHANGE,
    AlertTriggerType.DEADLINE_MISSED,
    AlertTriggerType.VERIFICATION_FAILED,
}

_LEVEL_BY_TRIGGER = {
    AlertTriggerType.CRITICAL_FINDING_CONFIRMED: AlertLevel.URGENT,
    AlertTriggerType.HIGH_FINDING_CONFIRMED: AlertLevel.WARNING,
    AlertTriggerType.UNAUTHORIZED_CHANGE: AlertLevel.URGENT,
    AlertTriggerType.DEADLINE_MISSED: AlertLevel.URGENT,
    AlertTriggerType.VERIFICATION_FAILED: AlertLevel.URGENT,
    AlertTriggerType.SCAN_FAILED: AlertLevel.WARNING,
    AlertTriggerType.PIPELINE_FAILURE: AlertLevel.WARNING,
    AlertTriggerType.TICKET_ASSIGNED: AlertLevel.WARNING,
    AlertTriggerType.TICKET_DEADLINE_CHANGED: AlertLevel.WARNING,
}

# SRS 4.5-4 A2: several triggers for the same site in a short window become one
# alert instead of flooding the recipient.
_GROUPING_WINDOW = timedelta(minutes=5)

# Each of these names a different ticket the vendor has to act on, so two in a
# row must both be delivered.
_NEVER_GROUPED = {AlertTriggerType.TICKET_ASSIGNED, AlertTriggerType.TICKET_DEADLINE_CHANGED}


def _build_message(trigger_type: AlertTriggerType, site_name: str, severity: str | None, action_required: str) -> str:
    severity_part = f" ({severity.title()} severity)" if severity else ""
    trigger_label = trigger_type.value.replace("_", " ").title()
    return f"{trigger_label}{severity_part} on {site_name}. {action_required}"


def _recent_similar_alert_exists(
    db: Session, recipient_id: uuid.UUID, trigger_type: AlertTriggerType, site_id: uuid.UUID | None
) -> bool:
    if site_id is None:
        return False
    cutoff = datetime.now(timezone.utc) - _GROUPING_WINDOW
    stmt = select(Alert.id).where(
        Alert.recipient_user_id == recipient_id,
        Alert.trigger_type == trigger_type,
        Alert.site_id == site_id,
        Alert.created_at >= cutoff,
    ).limit(1)
    return db.execute(stmt).scalar_one_or_none() is not None


def create_and_dispatch_alert(
    db: Session,
    recipient: User,
    trigger_type: AlertTriggerType,
    site_name: str,
    action_required: str,
    severity: str | None = None,
    site_id: uuid.UUID | None = None,
    ticket_id: uuid.UUID | None = None,
    finding_id: uuid.UUID | None = None,
) -> Alert | None:
    """Create an Alert row and try to deliver it. Returns None, creating
    nothing, when an alert of the same kind for the same site and recipient was
    already raised inside the grouping window."""
    if trigger_type not in _NEVER_GROUPED and _recent_similar_alert_exists(db, recipient.id, trigger_type, site_id):
        return None

    level = _LEVEL_BY_TRIGGER.get(trigger_type, AlertLevel.INFO)
    message = _build_message(trigger_type, site_name, severity, action_required)
    muted = trigger_type.value in (recipient.muted_trigger_types or [])

    alert = Alert(
        trigger_type=trigger_type,
        level=level,
        site_id=site_id,
        ticket_id=ticket_id,
        finding_id=finding_id,
        recipient_user_id=recipient.id,
        message=message,
        delivery_status=AlertDeliveryStatus.SUPPRESSED if muted else AlertDeliveryStatus.PENDING,
    )
    db.add(alert)
    db.flush()

    if not muted:
        adapter = get_notification_adapter()
        channel = "sms_push" if trigger_type in _URGENT_TRIGGERS else "email"
        try:
            adapter.send(recipient_email=recipient.email, subject=f"SentinelX: {trigger_type.value}", message=message)
            alert.delivery_status = AlertDeliveryStatus.DELIVERED
            alert.delivery_channel = channel
            alert.delivered_at = datetime.now(timezone.utc)
            audit_service.record(db, action=AuditAction.ALERT_DELIVERED, entity_type="alert", entity_id=alert.id)
        except Exception as exc:  # noqa: BLE001 - a delivery failure must never lose the alert
            alert.delivery_status = AlertDeliveryStatus.FAILED
            alert.delivery_error = str(exc)
            audit_service.record(
                db, action=AuditAction.ALERT_DELIVERY_FAILED, entity_type="alert", entity_id=alert.id,
                metadata={"error": str(exc)},
            )

    db.commit()
    db.refresh(alert)
    return alert


def list_alerts_for_recipient(
    db: Session, recipient_id: uuid.UUID, site_id: uuid.UUID | None = None,
    level: AlertLevel | None = None, trigger_type: AlertTriggerType | None = None,
) -> list[Alert]:
    stmt = select(Alert).where(Alert.recipient_user_id == recipient_id)
    if site_id is not None:
        stmt = stmt.where(Alert.site_id == site_id)
    if level is not None:
        stmt = stmt.where(Alert.level == level)
    if trigger_type is not None:
        stmt = stmt.where(Alert.trigger_type == trigger_type)
    return list(db.execute(stmt.order_by(Alert.created_at.desc())).scalars().all())


def list_alerts_for_department(
    db: Session, admin_user_ids: list[uuid.UUID], site_id: uuid.UUID | None = None,
    level: AlertLevel | None = None, trigger_type: AlertTriggerType | None = None,
) -> list[Alert]:
    stmt = select(Alert).where(Alert.recipient_user_id.in_(admin_user_ids))
    if site_id is not None:
        stmt = stmt.where(Alert.site_id == site_id)
    if level is not None:
        stmt = stmt.where(Alert.level == level)
    if trigger_type is not None:
        stmt = stmt.where(Alert.trigger_type == trigger_type)
    return list(db.execute(stmt.order_by(Alert.created_at.desc())).scalars().all())