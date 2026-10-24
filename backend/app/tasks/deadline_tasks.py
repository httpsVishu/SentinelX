"""Celery task for the daily SLA/deadline check and overdue escalation.

Runs once daily via Celery Beat (see celery_app.py's beat_schedule). For
every OPEN ticket past its deadline: marks it OVERDUE, alerts the Admin,
reminds the Vendor, and the vendor's scorecard automatically reflects the
change on next computation (scorecard_service.py reads live ticket status,
so no separate "update scorecard" write is needed here).
"""
from sqlalchemy import select

from app.database import SessionLocal
from app.models.enums import AlertTriggerType, UserRole
from app.models.site import Site
from app.models.user import User
from app.services import ticket_service
from app.services.alert_service import create_and_dispatch_alert
from app.tasks.celery_app import celery_app


@celery_app.task(name="app.tasks.deadline_tasks.check_overdue_tickets")
def check_overdue_tickets() -> None:
    db = SessionLocal()
    try:
        tickets_past_deadline = ticket_service.list_open_tickets_past_deadline(db)

        for ticket in tickets_past_deadline:
            changed = ticket_service.mark_overdue_if_past_deadline(db, ticket)
            if not changed:
                continue

            site = db.execute(select(Site).where(Site.id == ticket.site_id)).scalar_one()

            # Alert every Admin in the department (SRS 4.5-4: "the list of
            # people notified for a given site shall be configurable" — MVP
            # implementation notifies all department Admins by default).
            admins = db.execute(
                select(User).where(User.department_id == site.department_id, User.role == UserRole.ADMIN)
            ).scalars().all()
            for admin in admins:
                create_and_dispatch_alert(
                    db, admin, AlertTriggerType.DEADLINE_MISSED,
                    site_name=site.name,
                    action_required="Review the overdue ticket and follow up with the assigned vendor.",
                    severity=ticket.severity.value,
                    site_id=site.id, ticket_id=ticket.id,
                )

            # Remind the assigned vendor's users.
            if ticket.vendor_id is not None:
                vendor_users = db.execute(
                    select(User).where(User.vendor_id == ticket.vendor_id)
                ).scalars().all()
                for vendor_user in vendor_users:
                    create_and_dispatch_alert(
                        db, vendor_user, AlertTriggerType.DEADLINE_MISSED,
                        site_name=site.name,
                        action_required="This ticket's deadline has passed. Please submit a remediation as soon as possible.",
                        severity=ticket.severity.value,
                        site_id=site.id, ticket_id=ticket.id,
                    )
    finally:
        db.close()