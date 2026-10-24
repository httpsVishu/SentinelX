"""Demo data for local development.

Run with `make seed`, or `docker compose exec backend python -m app.seed.seed_data`.
Creates one department, one admin, two vendors with a login each, two practice
target sites (Juice Shop and DVWA, both self-hosted), a pending finding, and
tickets in three states (open, overdue, verified closed) with the history the
scorecards need, plus a few alerts.

The accounts and passwords here are development-only and are not real secrets.
"""
from datetime import datetime, timedelta, timezone

from app.core.crypto import encrypt_text
from app.core.security import hash_password
from app.database import SessionLocal, ensure_pgcrypto_extension
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
    VerificationResult,
)
from app.models.finding import Finding
from app.models.scan import Scan
from app.models.site import Site
from app.models.sla_config import SLAConfig
from app.models.ticket import RemediationSubmission, Ticket, VerificationRecord
from app.models.user import User
from app.models.vendor import Vendor

DEV_ADMIN_EMAIL = "admin@hansraj.sentinelx.local"
DEV_VENDOR_A_EMAIL = "vendor-a@sentinelx.local"
DEV_VENDOR_B_EMAIL = "vendor-b@sentinelx.local"
DEV_PASSWORD = "DevOnly!Passw0rd"  # noqa: S105 - development-only seed credential


def _ago(days: float = 0, hours: float = 0) -> datetime:
    return datetime.now(timezone.utc) - timedelta(days=days, hours=hours)


def _ahead(days: float) -> datetime:
    return datetime.now(timezone.utc) + timedelta(days=days)


def seed() -> None:
    ensure_pgcrypto_extension()
    db = SessionLocal()
    try:
        if db.query(Department).first() is not None:
            print("Seed data already present, skipping. Remove the database volume to reseed.")
            return

        department = Department(name="Hansraj College, Department of Computer Science")
        db.add(department)
        db.flush()

        db.add(SLAConfig(department_id=department.id, critical_days=3, high_days=7, medium_days=15, low_days=30))

        password_hash = hash_password(DEV_PASSWORD)
        admin = User(
            department_id=department.id, email=DEV_ADMIN_EMAIL, hashed_password=password_hash,
            full_name="Department Admin", role=UserRole.ADMIN, is_active=True,
        )
        db.add(admin)

        vendor_a = Vendor(
            department_id=department.id, name="Webnexus Solutions",
            contact_email="ops@webnexus.example", contact_phone="+91-9800000001",
        )
        vendor_b = Vendor(
            department_id=department.id, name="Brightline IT Services",
            contact_email="support@brightline.example", contact_phone="+91-9800000002",
        )
        db.add_all([vendor_a, vendor_b])
        db.flush()

        vendor_a_user = User(
            department_id=department.id, vendor_id=vendor_a.id, email=DEV_VENDOR_A_EMAIL,
            hashed_password=password_hash, full_name="Webnexus Ops", role=UserRole.VENDOR, is_active=True,
        )
        vendor_b_user = User(
            department_id=department.id, vendor_id=vendor_b.id, email=DEV_VENDOR_B_EMAIL,
            hashed_password=password_hash, full_name="Brightline Support", role=UserRole.VENDOR, is_active=True,
        )
        db.add_all([vendor_a_user, vendor_b_user])
        db.flush()

        # ---- Self-hosted practice targets ----
        juice_shop = Site(
            department_id=department.id, name="OWASP Juice Shop (practice target)",
            url="http://juice-shop.local:3000", vendor_id=vendor_a.id, scan_frequency_days=7,
            excluded_paths=["/admin"], is_active=True, is_gov_in=False, last_scanned_at=_ago(days=2),
        )
        dvwa = Site(
            department_id=department.id, name="DVWA (practice target)",
            url="http://dvwa.local:8080", vendor_id=vendor_b.id, scan_frequency_days=7,
            excluded_paths=[], is_active=True, is_gov_in=False, last_scanned_at=_ago(days=1),
        )
        db.add_all([juice_shop, dvwa])
        db.flush()

        scan_juice = Scan(
            site_id=juice_shop.id, trigger_type=ScanTriggerType.SCHEDULED, status=ScanStatus.COMPLETED,
            started_at=_ago(days=2, hours=0.4), completed_at=_ago(days=2),
        )
        scan_dvwa = Scan(
            site_id=dvwa.id, trigger_type=ScanTriggerType.SCHEDULED, status=ScanStatus.COMPLETED,
            started_at=_ago(days=1, hours=0.4), completed_at=_ago(days=1),
        )
        db.add_all([scan_juice, scan_dvwa])
        db.flush()

        # ---- 1. A finding waiting for the admin ----
        finding_pending = Finding(
            site_id=juice_shop.id, scan_id=scan_juice.id,
            title="Reflected Cross-Site Scripting on search endpoint",
            description="The product search endpoint reflects unsanitized user input back into the HTML response.",
            severity=Severity.HIGH, owasp_category="A03:2021 - Injection", confidence=0.86,
            affected_endpoint="/rest/products/search", status=FindingStatus.PENDING_ADMIN_REVIEW,
            raw_scanner_output_encrypted=encrypt_text(db, "mock raw scanner output for the XSS finding"),
            poc_summary_encrypted=encrypt_text(db, "Confirmed with a safe reflected marker. No script was executed."),
            validated_at=_ago(days=2),
        )

        # ---- 2. An approved finding with an open ticket ----
        finding_open = Finding(
            site_id=dvwa.id, scan_id=scan_dvwa.id, title="SQL Injection in login form",
            description="The login form's username parameter is passed into a backend query without parameterization.",
            severity=Severity.CRITICAL, owasp_category="A03:2021 - Injection", confidence=0.95,
            affected_endpoint="/vulnerabilities/sqli/", status=FindingStatus.APPROVED,
            raw_scanner_output_encrypted=encrypt_text(db, "mock raw boolean-injection evidence"),
            poc_summary_encrypted=encrypt_text(db, "Confirmed from a difference in query behaviour. No data was read."),
            plain_language_report=(
                "A SQL injection weakness was confirmed in the login form. An attacker could change the "
                "backend query to bypass sign-in or reach data they should not see."
            ),
            remediation_guidance="Use parameterized queries or the framework's data layer for every query on this form.",
            validated_at=_ago(days=1),
        )

        # ---- 3. An approved finding whose ticket is overdue ----
        finding_overdue = Finding(
            site_id=dvwa.id, scan_id=scan_dvwa.id, title="Weak session cookie attributes",
            description="Session cookies are issued without the Secure or HttpOnly attributes.",
            severity=Severity.MEDIUM, owasp_category="A05:2021 - Security Misconfiguration", confidence=0.82,
            affected_endpoint="/login.php", status=FindingStatus.APPROVED,
            raw_scanner_output_encrypted=encrypt_text(db, "mock raw cookie header evidence"),
            poc_summary_encrypted=encrypt_text(db, "Confirmed by reading the response headers of the sign-in page."),
            plain_language_report=(
                "Session cookies on the sign-in flow lack protective attributes, which makes it easier for "
                "a session to be stolen from a user's browser."
            ),
            remediation_guidance="Set the Secure and HttpOnly attributes and a SameSite policy on session cookies.",
            validated_at=_ago(days=17),
        )

        # ---- 4. A finding that was fixed and verified, for scorecard history ----
        finding_closed = Finding(
            site_id=juice_shop.id, scan_id=scan_juice.id,
            title="Outdated client-side JavaScript library with known CVEs",
            description="A bundled front-end library is several releases behind current.",
            severity=Severity.MEDIUM, owasp_category="A06:2021 - Vulnerable Components", confidence=0.78,
            affected_endpoint="/assets/vendor.js", status=FindingStatus.APPROVED,
            raw_scanner_output_encrypted=encrypt_text(db, "mock raw dependency check output"),
            poc_summary_encrypted=encrypt_text(db, "Confirmed by comparing the library version with public advisories."),
            plain_language_report="An outdated JavaScript dependency with known public vulnerabilities is in use.",
            remediation_guidance="Upgrade the library to the latest patched release and redeploy.",
            validated_at=_ago(days=20),
        )
        db.add_all([finding_pending, finding_open, finding_overdue, finding_closed])
        db.flush()

        ticket_open = Ticket(
            finding_id=finding_open.id, site_id=dvwa.id, vendor_id=vendor_b.id, severity=Severity.CRITICAL,
            status=TicketStatus.OPEN, deadline=_ahead(2), suggested_deadline=_ahead(2),
            deadline_source=DeadlineSource.AUTO, created_at=_ago(days=1),
        )
        ticket_overdue = Ticket(
            finding_id=finding_overdue.id, site_id=dvwa.id, vendor_id=vendor_b.id, severity=Severity.MEDIUM,
            status=TicketStatus.OVERDUE, deadline=_ago(days=2), suggested_deadline=_ago(days=2),
            deadline_source=DeadlineSource.AUTO, created_at=_ago(days=17), became_overdue_at=_ago(days=1),
        )
        ticket_closed = Ticket(
            finding_id=finding_closed.id, site_id=juice_shop.id, vendor_id=vendor_a.id, severity=Severity.MEDIUM,
            status=TicketStatus.VERIFIED_CLOSED, deadline=_ago(days=5), suggested_deadline=_ago(days=5),
            deadline_source=DeadlineSource.AUTO, created_at=_ago(days=20), closed_at=_ago(days=4),
        )
        db.add_all([ticket_open, ticket_overdue, ticket_closed])
        db.flush()

        db.add(RemediationSubmission(
            ticket_id=ticket_closed.id, vendor_user_id=vendor_a_user.id,
            note="Upgraded the vendor.js bundle to the latest release and redeployed.",
            submitted_at=_ago(days=6),
        ))
        verification_scan = Scan(
            site_id=juice_shop.id, trigger_type=ScanTriggerType.VERIFICATION, status=ScanStatus.COMPLETED,
            target_scope=["/assets/vendor.js"], verification_ticket_id=ticket_closed.id,
            started_at=_ago(days=4, hours=0.2), completed_at=_ago(days=4),
        )
        db.add(verification_scan)
        db.flush()
        db.add(VerificationRecord(
            ticket_id=ticket_closed.id, scan_id=verification_scan.id, result=VerificationResult.PASSED,
            notes="The library version is current and the re-scan found nothing.", verified_at=_ago(days=4),
        ))

        # ---- A few alerts ----
        db.add_all([
            Alert(
                trigger_type=AlertTriggerType.CRITICAL_FINDING_CONFIRMED, level=AlertLevel.URGENT,
                site_id=dvwa.id, finding_id=finding_open.id, ticket_id=ticket_open.id, recipient_user_id=admin.id,
                message="Critical Finding Confirmed (Critical severity) on DVWA (practice target). Review the finding in the review queue.",
                delivery_status=AlertDeliveryStatus.DELIVERED, delivery_channel="dev_console", delivered_at=_ago(days=1),
            ),
            Alert(
                trigger_type=AlertTriggerType.DEADLINE_MISSED, level=AlertLevel.URGENT,
                site_id=dvwa.id, ticket_id=ticket_overdue.id, recipient_user_id=admin.id,
                message="Deadline Missed (Medium severity) on DVWA (practice target). Review the overdue ticket and follow up with the assigned vendor.",
                delivery_status=AlertDeliveryStatus.DELIVERED, delivery_channel="dev_console", delivered_at=_ago(days=1),
            ),
            Alert(
                trigger_type=AlertTriggerType.DEADLINE_MISSED, level=AlertLevel.URGENT,
                site_id=dvwa.id, ticket_id=ticket_overdue.id, recipient_user_id=vendor_b_user.id,
                message="Deadline Missed (Medium severity) on DVWA (practice target). This ticket's deadline has passed. Please submit a remediation as soon as possible.",
                delivery_status=AlertDeliveryStatus.DELIVERED, delivery_channel="dev_console", delivered_at=_ago(days=1),
            ),
        ])

        db.commit()

        print("Seed complete. Development-only accounts, not for any other environment:")
        print(f"  Admin     {DEV_ADMIN_EMAIL}")
        print(f"  Vendor A  {DEV_VENDOR_A_EMAIL}")
        print(f"  Vendor B  {DEV_VENDOR_B_EMAIL}")
        print(f"  Password  {DEV_PASSWORD}")
    finally:
        db.close()


if __name__ == "__main__":
    seed()