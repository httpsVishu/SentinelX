"""Small helpers shared by the lifecycle tests."""
from sqlalchemy import select

from app.models.alert import Alert
from app.models.audit_log import AuditLog
from tests.factories import bearer

API = "/api/v1"

# The mock scanner reports this finding for any site whose URL contains "juice".
XSS_TITLE = "Reflected Cross-Site Scripting on search endpoint"
XSS_ENDPOINT = "/rest/products/search"


def audit_actions(db, entity_id):
    return list(db.execute(select(AuditLog.action).where(AuditLog.entity_id == entity_id)).scalars().all())


def alerts_for(db, user, trigger=None):
    stmt = select(Alert).where(Alert.recipient_user_id == user.id)
    if trigger is not None:
        stmt = stmt.where(Alert.trigger_type == trigger)
    return list(db.execute(stmt).scalars().all())


def submit_fix(client, vendor_user, ticket, note="Applied the fix."):
    return client.post(
        f"{API}/tickets/mine/{ticket.id}/remediate", headers=bearer(vendor_user), json={"note": note}
    )