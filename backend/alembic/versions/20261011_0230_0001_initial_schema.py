"""Initial schema

Revision ID: 0001
Revises:
Create Date: 2026-10-11 02:30:00 UTC

Creates every table in app/models, the pgcrypto extension, and three
database-level rules from the SRS that the services also enforce:

  - A finding cannot be Confirmed, Pending Review or Approved without a
    validation timestamp (ck_findings_validated_when_confirmed).
  - A ticket cannot be Verified and Closed without a passed re-scan record
    (deferred constraint trigger, checked at commit so the service can write
    the record and the status in one transaction).
  - A ticket has a vendor unless it is Unassigned, and a deadline override
    always carries a reason.

Enum labels are the Python member NAMES (for example VERIFIED_CLOSED), which
is what SQLAlchemy stores when it maps a Python Enum class. Raw SQL that
touches these columns must use the uppercase names.
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_SEVERITY = ("CRITICAL", "HIGH", "MEDIUM", "LOW", "INFORMATIONAL")

ENUMS: dict[str, tuple[str, ...]] = {
    "user_role": ("ADMIN", "VENDOR"),
    "severity": _SEVERITY,
    "ticket_severity": _SEVERITY,
    "finding_status": (
        "RAW", "CONFIRMED", "DISCARDED", "INCONCLUSIVE", "NEEDS_MANUAL_REVIEW",
        "PENDING_ADMIN_REVIEW", "APPROVED", "REJECTED",
    ),
    "ticket_status": (
        "UNASSIGNED", "OPEN", "OVERDUE", "FIX_SUBMITTED_PENDING_VERIFICATION",
        "VERIFIED_CLOSED", "FIX_FAILED_REOPENED",
    ),
    "deadline_source": ("AUTO", "OVERRIDE"),
    "scan_trigger_type": ("SCHEDULED", "MANUAL", "VERIFICATION"),
    "scan_status": ("QUEUED", "RUNNING", "COMPLETED", "FAILED"),
    "agent_name": (
        "RECON", "MAPPING", "ASSESSMENT", "VALIDATION", "REPORTING", "ACCOUNTABILITY", "VERIFICATION",
    ),
    "agent_execution_status": ("RUNNING", "SUCCEEDED", "FAILED"),
    "review_decision": ("APPROVE", "REJECT"),
    "verification_result": ("PASSED", "FAILED"),
    "alert_trigger_type": (
        "CRITICAL_FINDING_CONFIRMED", "HIGH_FINDING_CONFIRMED", "UNAUTHORIZED_CHANGE",
        "DEADLINE_MISSED", "VERIFICATION_FAILED", "SCAN_FAILED", "PIPELINE_FAILURE",
    ),
    "alert_level": ("URGENT", "WARNING", "INFO"),
    "alert_delivery_status": ("PENDING", "DELIVERED", "FAILED", "SUPPRESSED"),
    "audit_action": (
        "LOGIN_SUCCESS", "LOGIN_FAILURE", "FINDING_VALIDATED", "FINDING_APPROVED", "FINDING_REJECTED",
        "TICKET_CREATED", "TICKET_VENDOR_ASSIGNED", "TICKET_DEADLINE_OVERRIDDEN", "REMEDIATION_SUBMITTED",
        "VERIFICATION_PASSED", "VERIFICATION_FAILED", "TICKET_CLOSED", "ALERT_DELIVERED",
        "ALERT_DELIVERY_FAILED", "AGENT_EXECUTION_STARTED", "AGENT_EXECUTION_COMPLETED",
        "AGENT_EXECUTION_FAILED", "SCAN_TRIGGERED", "SCAN_QUEUED_DUPLICATE", "SITE_SCHEDULE_UPDATED",
        "SITE_EXCLUSIONS_UPDATED", "AUTHORIZATION_RECORD_ADDED",
    ),
}


def _enum(name: str) -> postgresql.ENUM:
    # create_type=False: the types are created once, explicitly, in upgrade().
    return postgresql.ENUM(*ENUMS[name], name=name, create_type=False)


def _pk() -> sa.Column:
    return sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True)


def _uuid(name: str, nullable: bool = False) -> sa.Column:
    return sa.Column(name, postgresql.UUID(as_uuid=True), nullable=nullable)


def _fk(name: str, target: str, ondelete: str, nullable: bool = False) -> sa.Column:
    return sa.Column(
        name, postgresql.UUID(as_uuid=True), sa.ForeignKey(target, ondelete=ondelete), nullable=nullable
    )


def _tz(name: str, nullable: bool = True, now: bool = False) -> sa.Column:
    return sa.Column(
        name,
        sa.DateTime(timezone=True),
        server_default=sa.text("now()") if now else None,
        nullable=nullable,
    )


def _created() -> sa.Column:
    return _tz("created_at", nullable=False, now=True)


def _updated() -> sa.Column:
    return _tz("updated_at", nullable=False, now=True)


def upgrade() -> None:
    bind = op.get_bind()

    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")
    for name, labels in ENUMS.items():
        postgresql.ENUM(*labels, name=name).create(bind, checkfirst=True)

    # ---- departments ----
    op.create_table(
        "departments",
        _pk(),
        sa.Column("name", sa.String(255), nullable=False),
        _created(),
        _updated(),
        sa.UniqueConstraint("name", name="uq_departments_name"),
    )

    # ---- vendors ----
    op.create_table(
        "vendors",
        _pk(),
        _fk("department_id", "departments.id", "CASCADE"),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("contact_email", sa.String(320), nullable=False),
        sa.Column("contact_phone", sa.String(32), nullable=True),
        _created(),
        _updated(),
    )
    op.create_index("ix_vendors_department_id", "vendors", ["department_id"])

    # ---- users ----
    op.create_table(
        "users",
        _pk(),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("hashed_password", sa.String(255), nullable=False),
        sa.Column("full_name", sa.String(255), nullable=False),
        sa.Column("role", _enum("user_role"), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        _fk("department_id", "departments.id", "CASCADE"),
        _fk("vendor_id", "vendors.id", "CASCADE", nullable=True),
        sa.Column(
            "muted_trigger_types",
            postgresql.ARRAY(sa.String(64)),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
        _created(),
        _updated(),
        _tz("last_login_at"),
        # A vendor login belongs to a vendor, and an admin login does not.
        sa.CheckConstraint(
            "(role = 'VENDOR' AND vendor_id IS NOT NULL) OR (role = 'ADMIN' AND vendor_id IS NULL)",
            name="ck_users_vendor_matches_role",
        ),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)
    op.create_index("ix_users_role", "users", ["role"])
    op.create_index("ix_users_vendor_id", "users", ["vendor_id"])

    # ---- sites ----
    op.create_table(
        "sites",
        _pk(),
        _fk("department_id", "departments.id", "CASCADE"),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("url", sa.String(2048), nullable=False),
        _fk("vendor_id", "vendors.id", "SET NULL", nullable=True),
        sa.Column("scan_frequency_days", sa.Integer(), nullable=False),
        sa.Column(
            "excluded_paths",
            postgresql.ARRAY(sa.String(1024)),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("is_gov_in", sa.Boolean(), nullable=False),
        _created(),
        _updated(),
        _tz("last_scanned_at"),
        sa.CheckConstraint("scan_frequency_days >= 1", name="ck_sites_scan_frequency_positive"),
    )
    op.create_index("ix_sites_department_id", "sites", ["department_id"])
    op.create_index("ix_sites_vendor_id", "sites", ["vendor_id"])

    # ---- authorization_records ----
    op.create_table(
        "authorization_records",
        _pk(),
        _fk("site_id", "sites.id", "CASCADE"),
        sa.Column("document_reference", sa.String(512), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        _fk("granted_by_user_id", "users.id", "RESTRICT"),
        _tz("granted_at", nullable=False),
        _created(),
    )
    op.create_index("ix_authorization_records_site_id", "authorization_records", ["site_id"])

    # ---- sla_configs ----
    op.create_table(
        "sla_configs",
        _pk(),
        _fk("department_id", "departments.id", "CASCADE"),
        sa.Column("critical_days", sa.Integer(), nullable=False),
        sa.Column("high_days", sa.Integer(), nullable=False),
        sa.Column("medium_days", sa.Integer(), nullable=False),
        sa.Column("low_days", sa.Integer(), nullable=False),
        _tz("effective_from", nullable=False, now=True),
        _created(),
        sa.CheckConstraint(
            "critical_days >= 1 AND high_days >= 1 AND medium_days >= 1 AND low_days >= 1",
            name="ck_sla_configs_days_positive",
        ),
    )
    op.create_index("ix_sla_configs_department_id", "sla_configs", ["department_id"])

    # ---- scans ----
    # verification_ticket_id points at tickets, which points (through
    # findings) back at scans. The foreign key is added after tickets exist.
    op.create_table(
        "scans",
        _pk(),
        _fk("site_id", "sites.id", "CASCADE"),
        sa.Column("trigger_type", _enum("scan_trigger_type"), nullable=False),
        sa.Column("status", _enum("scan_status"), nullable=False),
        sa.Column("target_scope", postgresql.ARRAY(sa.String(1024)), nullable=True),
        _uuid("verification_ticket_id", nullable=True),
        _fk("triggered_by_user_id", "users.id", "SET NULL", nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        _tz("queued_at", nullable=False, now=True),
        _tz("started_at"),
        _tz("completed_at"),
    )
    op.create_index("ix_scans_site_id", "scans", ["site_id"])
    op.create_index("ix_scans_status", "scans", ["status"])

    # ---- agent_executions ----
    op.create_table(
        "agent_executions",
        _pk(),
        _fk("scan_id", "scans.id", "CASCADE"),
        sa.Column("agent_name", _enum("agent_name"), nullable=False),
        sa.Column("status", _enum("agent_execution_status"), nullable=False),
        sa.Column("input_snapshot", postgresql.JSONB(), nullable=False),
        sa.Column("output_snapshot", postgresql.JSONB(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        _tz("started_at", nullable=False, now=True),
        _tz("completed_at"),
    )
    op.create_index("ix_agent_executions_scan_id", "agent_executions", ["scan_id"])
    op.create_index("ix_agent_executions_agent_name", "agent_executions", ["agent_name"])

    # ---- findings ----
    op.create_table(
        "findings",
        _pk(),
        _fk("site_id", "sites.id", "CASCADE"),
        _fk("scan_id", "scans.id", "CASCADE"),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("severity", _enum("severity"), nullable=False),
        sa.Column("owasp_category", sa.String(255), nullable=True),
        sa.Column("confidence", sa.Numeric(4, 3), nullable=False),
        sa.Column("affected_endpoint", sa.String(2048), nullable=False),
        sa.Column("status", _enum("finding_status"), nullable=False),
        sa.Column("raw_scanner_output_encrypted", sa.LargeBinary(), nullable=True),
        sa.Column("poc_summary_encrypted", sa.LargeBinary(), nullable=True),
        sa.Column("plain_language_report", sa.Text(), nullable=True),
        sa.Column("remediation_guidance", sa.Text(), nullable=True),
        _tz("validated_at"),
        _created(),
        _updated(),
        sa.CheckConstraint(
            "status NOT IN ('CONFIRMED', 'PENDING_ADMIN_REVIEW', 'APPROVED') OR validated_at IS NOT NULL",
            name="ck_findings_validated_when_confirmed",
        ),
    )
    op.create_index("ix_findings_site_id", "findings", ["site_id"])
    op.create_index("ix_findings_scan_id", "findings", ["scan_id"])
    op.create_index("ix_findings_severity", "findings", ["severity"])
    op.create_index("ix_findings_status", "findings", ["status"])

    # ---- finding_reviews ----
    op.create_table(
        "finding_reviews",
        _pk(),
        _fk("finding_id", "findings.id", "CASCADE"),
        _fk("reviewer_id", "users.id", "RESTRICT"),
        sa.Column("decision", _enum("review_decision"), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        _tz("decided_at", nullable=False, now=True),
        # A rejection always carries a reason.
        sa.CheckConstraint(
            "decision <> 'REJECT' OR (reason IS NOT NULL AND length(trim(reason)) > 0)",
            name="ck_finding_reviews_reject_has_reason",
        ),
    )
    op.create_index("ix_finding_reviews_finding_id", "finding_reviews", ["finding_id"])

    # ---- tickets ----
    op.create_table(
        "tickets",
        _pk(),
        _fk("finding_id", "findings.id", "RESTRICT"),
        _fk("site_id", "sites.id", "RESTRICT"),
        _fk("vendor_id", "vendors.id", "RESTRICT", nullable=True),
        sa.Column("severity", _enum("ticket_severity"), nullable=False),
        sa.Column("status", _enum("ticket_status"), nullable=False),
        _tz("deadline", nullable=False),
        _tz("suggested_deadline", nullable=False),
        sa.Column("deadline_source", _enum("deadline_source"), nullable=False),
        sa.Column("override_reason", sa.Text(), nullable=True),
        _created(),
        _updated(),
        _tz("closed_at"),
        sa.UniqueConstraint("finding_id", name="uq_tickets_finding_id"),
        sa.CheckConstraint(
            "vendor_id IS NOT NULL OR status = 'UNASSIGNED'",
            name="ck_tickets_vendor_unless_unassigned",
        ),
        sa.CheckConstraint(
            "deadline_source <> 'OVERRIDE' OR (override_reason IS NOT NULL AND length(trim(override_reason)) > 0)",
            name="ck_tickets_override_has_reason",
        ),
    )
    op.create_index("ix_tickets_site_id", "tickets", ["site_id"])
    op.create_index("ix_tickets_vendor_id", "tickets", ["vendor_id"])
    op.create_index("ix_tickets_status", "tickets", ["status"])

    op.create_foreign_key(
        "fk_scans_verification_ticket_id_tickets",
        "scans",
        "tickets",
        ["verification_ticket_id"],
        ["id"],
        ondelete="SET NULL",
    )

    # ---- remediation_submissions ----
    op.create_table(
        "remediation_submissions",
        _pk(),
        _fk("ticket_id", "tickets.id", "CASCADE"),
        _fk("vendor_user_id", "users.id", "RESTRICT"),
        sa.Column("note", sa.Text(), nullable=False),
        _tz("submitted_at", nullable=False, now=True),
    )
    op.create_index("ix_remediation_submissions_ticket_id", "remediation_submissions", ["ticket_id"])

    # ---- verification_records ----
    op.create_table(
        "verification_records",
        _pk(),
        _fk("ticket_id", "tickets.id", "CASCADE"),
        _fk("scan_id", "scans.id", "RESTRICT"),
        sa.Column("result", _enum("verification_result"), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        _tz("verified_at", nullable=False, now=True),
    )
    op.create_index("ix_verification_records_ticket_id", "verification_records", ["ticket_id"])

    # ---- alerts ----
    op.create_table(
        "alerts",
        _pk(),
        sa.Column("trigger_type", _enum("alert_trigger_type"), nullable=False),
        sa.Column("level", _enum("alert_level"), nullable=False),
        _fk("site_id", "sites.id", "SET NULL", nullable=True),
        _fk("ticket_id", "tickets.id", "SET NULL", nullable=True),
        _fk("finding_id", "findings.id", "SET NULL", nullable=True),
        _fk("recipient_user_id", "users.id", "CASCADE"),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("delivery_status", _enum("alert_delivery_status"), nullable=False),
        sa.Column("delivery_channel", sa.Text(), nullable=True),
        sa.Column("delivery_error", sa.Text(), nullable=True),
        _created(),
        _tz("delivered_at"),
    )
    op.create_index("ix_alerts_trigger_type", "alerts", ["trigger_type"])
    op.create_index("ix_alerts_level", "alerts", ["level"])
    op.create_index("ix_alerts_recipient_user_id", "alerts", ["recipient_user_id"])
    op.create_index("ix_alerts_created_at", "alerts", ["created_at"])

    # ---- audit_logs ----
    op.create_table(
        "audit_logs",
        _pk(),
        _fk("actor_id", "users.id", "SET NULL", nullable=True),
        sa.Column("action", _enum("audit_action"), nullable=False),
        sa.Column("entity_type", sa.String(64), nullable=False),
        _uuid("entity_id", nullable=True),
        sa.Column("metadata_json", postgresql.JSONB(), nullable=False),
        _tz("timestamp", nullable=False, now=True),
    )
    op.create_index("ix_audit_logs_actor_id", "audit_logs", ["actor_id"])
    op.create_index("ix_audit_logs_action", "audit_logs", ["action"])
    op.create_index("ix_audit_logs_entity_type", "audit_logs", ["entity_type"])
    op.create_index("ix_audit_logs_entity_id", "audit_logs", ["entity_id"])
    op.create_index("ix_audit_logs_timestamp", "audit_logs", ["timestamp"])

    # ---- Ticket closure rule ----
    # Deferred to commit time, so a service can insert the verification record
    # and move the ticket in the same transaction, in either order.
    op.execute(
        """
        CREATE FUNCTION enforce_ticket_close_requires_pass() RETURNS trigger AS $$
        BEGIN
            IF NEW.status = 'VERIFIED_CLOSED' AND NOT EXISTS (
                SELECT 1 FROM verification_records
                WHERE ticket_id = NEW.id AND result = 'PASSED'
            ) THEN
                RAISE EXCEPTION 'Ticket % cannot be closed without a passed verification re-scan', NEW.id
                    USING ERRCODE = '23514';
            END IF;
            RETURN NULL;
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        """
        CREATE CONSTRAINT TRIGGER trg_ticket_close_requires_pass
        AFTER INSERT OR UPDATE OF status ON tickets
        DEFERRABLE INITIALLY DEFERRED
        FOR EACH ROW EXECUTE FUNCTION enforce_ticket_close_requires_pass()
        """
    )


def downgrade() -> None:
    bind = op.get_bind()

    op.execute("DROP TRIGGER IF EXISTS trg_ticket_close_requires_pass ON tickets")
    op.execute("DROP FUNCTION IF EXISTS enforce_ticket_close_requires_pass()")

    op.drop_table("audit_logs")
    op.drop_table("alerts")
    op.drop_constraint("fk_scans_verification_ticket_id_tickets", "scans", type_="foreignkey")
    op.drop_table("verification_records")
    op.drop_table("remediation_submissions")
    op.drop_table("tickets")
    op.drop_table("finding_reviews")
    op.drop_table("findings")
    op.drop_table("agent_executions")
    op.drop_table("scans")
    op.drop_table("sla_configs")
    op.drop_table("authorization_records")
    op.drop_table("sites")
    op.drop_table("users")
    op.drop_table("vendors")
    op.drop_table("departments")

    for name in ENUMS:
        postgresql.ENUM(name=name).drop(bind, checkfirst=True)
    # pgcrypto is left installed: other databases objects may rely on it.