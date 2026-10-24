"""Celery task: run the targeted re-scan after a Vendor reports a fix.

Outcomes:
  passed        ticket closed by ticket_service
  failed        ticket reopened, Admin and Vendor alerted
  inconclusive  ticket stays "fix submitted", the scan is marked failed, the
                Admin is alerted and can re-run verification from the ticket
"""
import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import select

from app.database import SessionLocal
from app.models.enums import AlertTriggerType, ScanStatus, ScanTriggerType, TicketStatus, UserRole
from app.models.finding import Finding
from app.models.scan import Scan
from app.models.site import Site
from app.models.ticket import Ticket
from app.models.user import User
from app.orchestration.graph import run_verification_pipeline
from app.services.alert_service import create_and_dispatch_alert
from app.tasks.celery_app import celery_app

logger = logging.getLogger("sentinelx.tasks.verification")


@celery_app.task(name="app.tasks.verification_tasks.run_verification_scan", bind=True, max_retries=1, default_retry_delay=30)
def run_verification_scan(self, ticket_id_str: str) -> None:
    ticket_id = uuid.UUID(ticket_id_str)
    db = SessionLocal()
    try:
        ticket = db.execute(select(Ticket).where(Ticket.id == ticket_id)).scalar_one_or_none()
        # Only a ticket with a submitted fix is verified. This also stops a
        # duplicate task from touching a ticket that was already decided.
        if ticket is None or ticket.status != TicketStatus.FIX_SUBMITTED_PENDING_VERIFICATION:
            return

        site = db.execute(select(Site).where(Site.id == ticket.site_id)).scalar_one()
        finding = db.execute(select(Finding).where(Finding.id == ticket.finding_id)).scalar_one()

        scan = Scan(
            site_id=site.id,
            trigger_type=ScanTriggerType.VERIFICATION,
            status=ScanStatus.RUNNING,
            target_scope=[finding.affected_endpoint],
            verification_ticket_id=ticket.id,
            started_at=datetime.now(timezone.utc),
        )
        db.add(scan)
        db.commit()
        db.refresh(scan)
        scan_id = scan.id

        final_state = None
        problem: str | None = None
        try:
            final_state = run_verification_pipeline(
                db, scan_id, ticket.id, site, finding.affected_endpoint, original_title=finding.title
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("Verification pipeline failed for ticket %s", ticket_id)
            problem = str(exc)
            db.rollback()

        scan = db.get(Scan, scan_id)
        ticket = db.get(Ticket, ticket_id)
        output = (final_state.verification_output if final_state else None) or {}
        result = output.get("result")

        admins = db.execute(
            select(User).where(User.department_id == site.department_id, User.role == UserRole.ADMIN)
        ).scalars().all()

        if result in ("passed", "failed"):
            scan.status = ScanStatus.COMPLETED
            scan.completed_at = datetime.now(timezone.utc)
            db.commit()
            if result == "failed":
                _alert_failed_fix(db, site, ticket, admins)
            return

        # Inconclusive, or the pipeline itself broke. Do not touch the ticket.
        errors = "; ".join(final_state.errors) if final_state else ""
        scan.status = ScanStatus.FAILED
        scan.error_message = problem or output.get("notes") or errors or "Verification could not be completed."
        scan.completed_at = datetime.now(timezone.utc)
        db.commit()
        for admin in admins:
            create_and_dispatch_alert(
                db,
                admin,
                AlertTriggerType.SCAN_FAILED,
                site_name=site.name,
                action_required=(
                    "A reported fix could not be checked automatically. Check the site, "
                    "then use Re-run verification on the ticket."
                ),
                severity=ticket.severity.value,
                site_id=site.id,
                ticket_id=ticket.id,
            )
    finally:
        db.close()


def _alert_failed_fix(db, site: Site, ticket: Ticket, admins: list[User]) -> None:
    """SRS 4.5-4 trigger (d): a claimed fix did not work."""
    for admin in admins:
        create_and_dispatch_alert(
            db,
            admin,
            AlertTriggerType.VERIFICATION_FAILED,
            site_name=site.name,
            action_required="The claimed fix did not pass re-verification. The ticket has been reopened.",
            severity=ticket.severity.value,
            site_id=site.id,
            ticket_id=ticket.id,
        )
    if ticket.vendor_id is None:
        return
    vendor_users = db.execute(select(User).where(User.vendor_id == ticket.vendor_id)).scalars().all()
    for vendor_user in vendor_users:
        create_and_dispatch_alert(
            db,
            vendor_user,
            AlertTriggerType.VERIFICATION_FAILED,
            site_name=site.name,
            action_required="Your submitted fix did not pass verification. Please review and resubmit.",
            severity=ticket.severity.value,
            site_id=site.id,
            ticket_id=ticket.id,
        )