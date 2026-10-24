"""AuthorizationService: enforces the IT Act 2000 scanning restriction.

A site whose URL falls under a restricted domain suffix (default: .gov.in,
see settings.RESTRICTED_DOMAIN_SUFFIXES) must have at least one
AuthorizationRecord on file before any scan (scheduled, manual or
verification) is permitted. This check must be called before a Scan row is
even created (see scan_service.py::trigger_scan()), not just before the
Recon Agent starts, so an unauthorized scan is never queued at all.
"""
import uuid
from urllib.parse import urlparse

from sqlalchemy import exists, select
from sqlalchemy.orm import Session

from app.config import settings
from app.models.authorization_record import AuthorizationRecord
from app.models.site import Site


class ScanNotAuthorizedError(Exception):
    """Raised when a scan is attempted against a restricted-domain site
    with no authorization record on file."""


def url_is_restricted_domain(url: str) -> bool:
    hostname = (urlparse(url).hostname or "").lower()
    return any(hostname.endswith(suffix.lower()) for suffix in settings.restricted_domain_suffixes_list)


def site_requires_authorization(site: Site) -> bool:
    """A site is treated as requiring authorization if either its stored
    is_gov_in flag is set, or its URL happens to match a restricted suffix
    (defense in depth in case is_gov_in was set incorrectly at creation)."""
    return site.is_gov_in or url_is_restricted_domain(site.url)


def list_authorization_records(db: Session, site_id: uuid.UUID) -> list[AuthorizationRecord]:
    """All authorization records for a site, newest grant first. The caller
    is responsible for checking the site belongs to the user's department."""
    stmt = (
        select(AuthorizationRecord)
        .where(AuthorizationRecord.site_id == site_id)
        .order_by(AuthorizationRecord.granted_at.desc())
    )
    return list(db.execute(stmt).scalars().all())


def assert_scan_is_authorized(db: Session, site: Site) -> None:
    """Raise ScanNotAuthorizedError unless scanning this site is currently
    permitted. Called once per scan trigger, before a Scan row is created."""
    if not site_requires_authorization(site):
        return

    has_record = db.execute(
        select(exists().where(AuthorizationRecord.site_id == site.id))
    ).scalar()

    if not has_record:
        raise ScanNotAuthorizedError(
            f"Site '{site.name}' ({site.url}) requires a stored written "
            "authorization record before it can be scanned, per Sections 43 "
            "and 66 of the Information Technology Act, 2000."
        )