"""Celery task: Reporting -> Accountability -> Ticket, after an Admin approves
a finding.

It runs in a worker with its own database session. The review endpoint used to
hand its request session to a background task, which can run after that
session is closed. If no ticket exists after the pipeline finishes, the task
retries, and after the last retry it alerts the admins so an approved finding
is never left without an owner and without anyone knowing.
"""
import logging
import uuid

from sqlalchemy import select

from app.database import SessionLocal
from app.models.enums import AlertTriggerType, FindingStatus, UserRole
from app.models.finding import Finding
from app.models.site import Site
from app.models.ticket import Ticket
from app.models.user import User
from app.orchestration.graph import run_post_approval_pipeline
from app.services.alert_service import create_and_dispatch_alert
from app.tasks.celery_app import celery_app

logger = logging.getLogger("sentinelx.tasks.approval")


@celery_app.task(name="app.tasks.approval_tasks.run_post_approval", bind=True, max_retries=2, default_retry_delay=30)
def run_post_approval(self, finding_id_str: str, department_id_str: str) -> None:
    finding_id = uuid.UUID(finding_id_str)
    department_id = uuid.UUID(department_id_str)

    db = SessionLocal()
    try:
        finding = db.execute(select(Finding).where(Finding.id == finding_id)).scalar_one_or_none()
        if finding is None or finding.status != FindingStatus.APPROVED:
            return

        try:
            run_post_approval_pipeline(db, finding.scan_id, finding, department_id)
        except Exception:  # noqa: BLE001
            logger.exception("Post-approval pipeline failed for finding %s", finding_id)
            db.rollback()

        has_ticket = db.execute(select(Ticket.id).where(Ticket.finding_id == finding_id)).first() is not None
        if has_ticket:
            return

        if self.request.retries < self.max_retries:
            raise self.retry(countdown=30)

        _alert_admins_of_failure(db, finding_id)
    finally:
        db.close()


def _alert_admins_of_failure(db, finding_id: uuid.UUID) -> None:
    finding = db.get(Finding, finding_id)
    site = db.get(Site, finding.site_id)
    admins = db.execute(
        select(User).where(User.department_id == site.department_id, User.role == UserRole.ADMIN)
    ).scalars().all()
    for admin in admins:
        create_and_dispatch_alert(
            db,
            admin,
            AlertTriggerType.PIPELINE_FAILURE,
            site_name=site.name,
            action_required=(
                "An approved finding has no ticket because the report or assignment step "
                "failed. Check the agent activity for the originating scan."
            ),
            severity=finding.severity.value,
            site_id=site.id,
            finding_id=finding.id,
        )