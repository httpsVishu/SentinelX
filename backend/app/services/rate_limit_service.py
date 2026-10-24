"""Login throttling, built on the audit log.

Failed logins are already recorded in audit_logs, so the limit reads them and
needs no extra table or Redis key. Two limits apply inside a rolling window:

  per email  5 failures, then the account is locked for that address
  per IP     20 failures across any addresses

The limit applies to any address, known or not, and a blocked attempt gets the
same message either way. A blocked attempt is not recorded as a failure, so it
cannot extend the lock. A successful login clears the earlier failures for that
address.
"""
import math
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.audit_log import AuditLog
from app.models.enums import AuditAction

WINDOW = timedelta(minutes=15)
MAX_FAILURES_PER_EMAIL = 5
MAX_FAILURES_PER_IP = 20


class RateLimitedError(Exception):
    def __init__(self, retry_after_seconds: int):
        self.retry_after = retry_after_seconds
        minutes = max(1, math.ceil(retry_after_seconds / 60))
        unit = "minute" if minutes == 1 else "minutes"
        super().__init__(f"Too many failed sign-in attempts. Try again in {minutes} {unit}.")


def normalize_email(email: str) -> str:
    return email.strip().lower()


def _failure_times(db: Session, field: str, value: str, since: datetime) -> list[datetime]:
    stmt = (
        select(AuditLog.timestamp)
        .where(
            AuditLog.action == AuditAction.LOGIN_FAILURE,
            AuditLog.timestamp >= since,
            AuditLog.metadata_json[field].as_string() == value,
        )
        .order_by(AuditLog.timestamp)
    )
    return list(db.execute(stmt).scalars().all())


def _last_success(db: Session, email: str) -> datetime | None:
    return db.execute(
        select(func.max(AuditLog.timestamp)).where(
            AuditLog.action == AuditAction.LOGIN_SUCCESS,
            AuditLog.metadata_json["email"].as_string() == email,
        )
    ).scalar()


def _wait(times: list[datetime], limit: int, now: datetime) -> int:
    """Seconds until fewer than `limit` of these failures are still in the
    window. `times` is sorted oldest first."""
    if len(times) < limit:
        return 0
    lifts_at = times[len(times) - limit] + WINDOW
    return max(1, math.ceil((lifts_at - now).total_seconds()))


def seconds_until_allowed(db: Session, email: str, ip: str | None, now: datetime | None = None) -> int:
    """0 when a login attempt may go ahead, otherwise how long to wait."""
    now = now or datetime.now(timezone.utc)
    window_start = now - WINDOW

    since_email = window_start
    last_success = _last_success(db, email)
    if last_success is not None and last_success > since_email:
        since_email = last_success

    waits = [_wait(_failure_times(db, "email", email, since_email), MAX_FAILURES_PER_EMAIL, now)]
    if ip:
        waits.append(_wait(_failure_times(db, "ip", ip, window_start), MAX_FAILURES_PER_IP, now))
    return max(waits)