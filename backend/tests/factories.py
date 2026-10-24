"""Row builders for tests. Each helper adds the row, flushes it and returns it,
so a test reads as a short list of facts about the world it needs."""
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from itertools import count

from sqlalchemy.orm import Session

from app.core.crypto import encrypt_text
from app.core.security import create_access_token, hash_password
from app.models.alert import Alert
from app.models.department import Department
from app.models.enums import (
    AlertDeliveryStatus,
    AlertLevel,
    AlertTriggerType,
    DeadlineSource,
    FindingStatus,
    ScanStatus,
    ScanTriggerType,
    Severity,
    TicketStatus,
    UserRole,
)
from app.models.finding import Finding
from app.models.scan import Scan
from app.models.site import Site
from app.models.sla_config import SLAConfig
from app.models.ticket import Ticket
from app.models.user import User
from app.models.vendor import Vendor

DEFAULT_PASSWORD = "TestPass!234"
POC_TEXT = "Confirmed with a read-only check of the endpoint."
RAW_OUTPUT_TEXT = "raw scanner output used only in tests"

_sequence = count(1)


def _next() -> int:
    return next(_sequence)


def _now() -> datetime:
    return datetime.now(timezone.utc)


@lru_cache
def _default_password_hash() -> str:
    # bcrypt is slow on purpose. Hash the shared test password once per run.
    return hash_password(DEFAULT_PASSWORD)


def make_department(db: Session, name: str | None = None, with_sla: bool = True) -> Department:
    department = Department(name=name or f"Test Department {_next()}")
    db.add(department)
    db.flush()
    if with_sla:
        db.add(
            SLAConfig(
                department_id=department.id,
                critical_days=3,
                high_days=7,
                medium_days=15,
                low_days=30,
                effective_from=_now() - timedelta(minutes=1),
            )
        )
        db.flush()
    return department


def make_admin(
    db: Session,
    department: Department,
    email: str | None = None,
    password: str = DEFAULT_PASSWORD,
    is_active: bool = True,
) -> User:
    user = User(
        department_id=department.id,
        email=email or f"admin{_next()}@example.com",
        hashed_password=_default_password_hash() if password == DEFAULT_PASSWORD else hash_password(password),
        full_name="Test Admin",
        role=UserRole.ADMIN,
        is_active=is_active,
    )
    db.add(user)
    db.flush()
    return user


def make_vendor(db: Session, department: Department, name: str | None = None, email: str | None = None) -> Vendor:
    number = _next()
    vendor = Vendor(
        department_id=department.id,
        name=name or f"Test Vendor {number}",
        contact_email=email or f"vendor{number}@example.com",
    )
    db.add(vendor)
    db.flush()
    return vendor


def make_vendor_user(
    db: Session,
    vendor: Vendor,
    email: str | None = None,
    password: str = DEFAULT_PASSWORD,
    is_active: bool = True,
) -> User:
    user = User(
        department_id=vendor.department_id,
        vendor_id=vendor.id,
        email=email or f"vendoruser{_next()}@example.com",
        hashed_password=_default_password_hash() if password == DEFAULT_PASSWORD else hash_password(password),
        full_name=f"{vendor.name} Ops",
        role=UserRole.VENDOR,
        is_active=is_active,
    )
    db.add(user)
    db.flush()
    return user


def make_site(
    db: Session,
    department: Department,
    vendor: Vendor | None = None,
    url: str = "http://juice-shop.local:3000",
    name: str | None = None,
    **overrides,
) -> Site:
    site = Site(
        department_id=department.id,
        vendor_id=vendor.id if vendor else None,
        name=name or f"Test Site {_next()}",
        url=url,
        scan_frequency_days=7,
        excluded_paths=[],
        is_active=True,
        is_gov_in=False,
    )
    for field, value in overrides.items():
        setattr(site, field, value)
    db.add(site)
    db.flush()
    return site


def make_scan(
    db: Session,
    site: Site,
    status: ScanStatus = ScanStatus.COMPLETED,
    trigger: ScanTriggerType = ScanTriggerType.SCHEDULED,
    target_scope: list[str] | None = None,
) -> Scan:
    scan = Scan(site_id=site.id, status=status, trigger_type=trigger, target_scope=target_scope)
    db.add(scan)
    db.flush()
    return scan


def make_finding(
    db: Session,
    site: Site,
    scan: Scan | None = None,
    severity: Severity = Severity.HIGH,
    status: FindingStatus = FindingStatus.PENDING_ADMIN_REVIEW,
    endpoint: str = "/rest/products/search",
    title: str | None = None,
) -> Finding:
    finding = Finding(
        site_id=site.id,
        scan_id=(scan or make_scan(db, site)).id,
        title=title or f"Test finding {_next()}",
        description="A description written for tests.",
        severity=severity,
        confidence=0.9,
        affected_endpoint=endpoint,
        status=status,
        raw_scanner_output_encrypted=encrypt_text(db, RAW_OUTPUT_TEXT),
        poc_summary_encrypted=encrypt_text(db, POC_TEXT),
        # The database requires this for Confirmed, Pending Review and Approved findings.
        validated_at=None if status == FindingStatus.RAW else _now(),
    )
    db.add(finding)
    db.flush()
    return finding


def make_ticket(
    db: Session,
    finding: Finding,
    vendor: Vendor | None,
    status: TicketStatus = TicketStatus.OPEN,
    deadline: datetime | None = None,
    created_at: datetime | None = None,
) -> Ticket:
    if vendor is None:
        status = TicketStatus.UNASSIGNED
    due = deadline or (_now() + timedelta(days=7))
    ticket = Ticket(
        finding_id=finding.id,
        site_id=finding.site_id,
        vendor_id=vendor.id if vendor else None,
        severity=finding.severity,
        status=status,
        deadline=due,
        suggested_deadline=due,
        deadline_source=DeadlineSource.AUTO,
    )
    if created_at is not None:
        ticket.created_at = created_at
    if status == TicketStatus.VERIFIED_CLOSED:
        ticket.closed_at = _now()
    db.add(ticket)
    db.flush()
    return ticket


def make_alert(
    db: Session,
    recipient: User,
    site: Site | None = None,
    ticket: Ticket | None = None,
    trigger: AlertTriggerType = AlertTriggerType.DEADLINE_MISSED,
    level: AlertLevel = AlertLevel.URGENT,
) -> Alert:
    alert = Alert(
        trigger_type=trigger,
        level=level,
        site_id=site.id if site else None,
        ticket_id=ticket.id if ticket else None,
        recipient_user_id=recipient.id,
        message="A test alert.",
        delivery_status=AlertDeliveryStatus.DELIVERED,
    )
    db.add(alert)
    db.flush()
    return alert


def bearer(user: User) -> dict[str, str]:
    """Authorization header for a user, without going through the login call."""
    token = create_access_token(user.id, user.role.value)
    return {"Authorization": f"Bearer {token}"}