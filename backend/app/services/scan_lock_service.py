"""PostgreSQL advisory locks used to serialize scans for one site.

The scans table intentionally allows several queued scans for a site. A
transactional row lock would be released by the commits made during the agent
pipeline, so it cannot protect the whole run. Session advisory locks stay held
until the worker explicitly releases them and therefore cover both full and
verification scans.
"""
import uuid

from sqlalchemy import text
from sqlalchemy.orm import Session


def _lock_keys(site_id: uuid.UUID) -> tuple[int, int]:
    """Map a UUID to PostgreSQL's two signed 32-bit advisory-lock keys."""
    first = int.from_bytes(site_id.bytes[:4], byteorder="big", signed=True)
    second = int.from_bytes(site_id.bytes[4:8], byteorder="big", signed=True)
    return first, second


def try_acquire_site_scan_lock(db: Session, site_id: uuid.UUID) -> bool:
    first, second = _lock_keys(site_id)
    return bool(
        db.execute(
            text("SELECT pg_try_advisory_lock(:first, :second)"),
            {"first": first, "second": second},
        ).scalar()
    )


def release_site_scan_lock(db: Session, site_id: uuid.UUID) -> None:
    first, second = _lock_keys(site_id)
    db.execute(
        text("SELECT pg_advisory_unlock(:first, :second)"),
        {"first": first, "second": second},
    )
