"""Celery application instance and configuration.

Imported by `celery -A app.tasks.celery_app worker` and
`celery -A app.tasks.celery_app beat` (see docker-compose.yml). Task modules
are listed explicitly in `include=` so Celery finds them.
"""
from celery import Celery
from celery.schedules import crontab

from app.config import settings

celery_app = Celery(
    "sentinelx",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
    include=[
        "app.tasks.scan_tasks",
        "app.tasks.deadline_tasks",
        "app.tasks.verification_tasks",
        "app.tasks.approval_tasks",
        "app.tasks.notification_tasks",
        "app.tasks.maintenance_tasks",
    ],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    # Crash safety. Scanner and LLM failures are already handled and shown as
    # scan or agent failures. This covers worker crashes and broker hiccups.
    task_acks_late=True,
    task_reject_on_worker_lost=True,
)

celery_app.conf.beat_schedule = {
    "check-site-scan-schedules": {
        "task": "app.tasks.scan_tasks.dispatch_due_scheduled_scans",
        "schedule": crontab(minute="0", hour="*"),  # hourly, against each site's own frequency
    },
    "daily-deadline-check": {
        "task": "app.tasks.deadline_tasks.check_overdue_tickets",
        "schedule": crontab(minute="0", hour="2"),  # daily at 02:00 UTC
    },
    "fail-stuck-scans": {
        "task": "app.tasks.maintenance_tasks.fail_stuck_scans",
        "schedule": crontab(minute="*/15"),
    },
}
