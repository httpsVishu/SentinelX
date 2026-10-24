"""Celery tasks for notification events that start outside the main request.

Alerts raised during a request through a service call are created directly by
app/services/alert_service.py. These tasks cover two cases: events discovered
inside other Celery tasks (a failed scan), and events whose delivery should not
slow down the request that caused them (a ticket assigned to a vendor).
"""
import uuid
from datetime import timezone

from sqlalchemy import select

from app.database import SessionLocal
from app.models.enums import AlertTriggerType, UserRole
from app.models.site import Site
from app.models.ticket import Ticket
from app.models.user import User
from app.services.alert_service import create_and_dispatch_alert
from app.tasks.celery_app import celery_app


@celery_app.task(name="app.tasks.notification_tasks.notify_scan_failed")
def notify_scan_failed(site_id_str: str, scan_id_str: str, error_message: str) -> None:
    # The error text is deliberately not part of the alert. It is on the scan.
    db = SessionLocal()
    try:
        site = db.execute(select(Site).where(Site.id == uuid.UUID(site_id_str))).scalar_one()
        admins = db.execute(
            select(User).where(User.department_id == site.department_id, User.role == UserRole.ADMIN)
        ).scalars().all()
        for admin in admins:
            create_and_dispatch_alert(
                db,
                admin,
                AlertTriggerType.SCAN_FAILED,
                site_name=site.name,
                action_required=f"A scan failed and needs attention. Reference: scan {scan_id_str}.",
                site_id=site.id,
            )
    finally:
        db.close()


_TICKET_CHANGE_TRIGGERS = {
    "assigned": AlertTriggerType.TICKET_ASSIGNED,
    "deadline_changed": AlertTriggerType.TICKET_DEADLINE_CHANGED,
}


@celery_app.task(name="app.tasks.notification_tasks.notify_vendor_of_ticket_change")
def notify_vendor_of_ticket_change(ticket_id_str: str, kind: str) -> None:
    """Tell every active login at the ticket's vendor that a ticket was
    assigned to them (SRS 4.3-4) or that its deadline changed. The message
    carries the severity, the site and the deadline, never the finding."""
    trigger = _TICKET_CHANGE_TRIGGERS[kind]  # a typo in `kind` fails loudly

    db = SessionLocal()
    try:
        ticket = db.get(Ticket, uuid.UUID(ticket_id_str))
        if ticket is None or ticket.vendor_id is None:
            return

        site = db.get(Site, ticket.site_id)
        when = ticket.deadline.astimezone(timezone.utc).strftime("%d %b %Y, %H:%M UTC")
        if kind == "assigned":
            action = f"Fix it by {when}. Open the ticket in SentinelX for details."
        else:
            action = f"The new deadline is {when}."

        logins = db.execute(
            select(User).where(User.vendor_id == ticket.vendor_id, User.is_active.is_(True))
        ).scalars().all()
        for login in logins:
            create_and_dispatch_alert(
                db,
                login,
                trigger,
                site_name=site.name,
                action_required=action,
                severity=ticket.severity.value,
                site_id=site.id,
                ticket_id=ticket.id,
            )
    finally:
        db.close()