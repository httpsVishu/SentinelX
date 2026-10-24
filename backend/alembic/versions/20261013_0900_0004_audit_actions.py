"""Add the vendor_created and site_created audit actions

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-13 09:00:00 UTC

Creating a vendor or a site used to be logged under unrelated actions. Labels
are the Python member NAMES, as in the initial migration.
"""
from collections.abc import Sequence

from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

NEW_LABELS = ("VENDOR_CREATED", "SITE_CREATED")

OLD_LABELS = (
    "LOGIN_SUCCESS", "LOGIN_FAILURE", "FINDING_VALIDATED", "FINDING_APPROVED", "FINDING_REJECTED",
    "TICKET_CREATED", "TICKET_VENDOR_ASSIGNED", "TICKET_DEADLINE_OVERRIDDEN", "REMEDIATION_SUBMITTED",
    "VERIFICATION_PASSED", "VERIFICATION_FAILED", "TICKET_CLOSED", "ALERT_DELIVERED",
    "ALERT_DELIVERY_FAILED", "AGENT_EXECUTION_STARTED", "AGENT_EXECUTION_COMPLETED",
    "AGENT_EXECUTION_FAILED", "SCAN_TRIGGERED", "SCAN_QUEUED_DUPLICATE", "SITE_SCHEDULE_UPDATED",
    "SITE_EXCLUSIONS_UPDATED", "AUTHORIZATION_RECORD_ADDED",
)


def upgrade() -> None:
    # On older PostgreSQL versions a new enum value cannot be added inside a
    # transaction block, so this step runs outside the migration's transaction.
    with op.get_context().autocommit_block():
        for label in NEW_LABELS:
            op.execute(f"ALTER TYPE audit_action ADD VALUE IF NOT EXISTS '{label}'")


def downgrade() -> None:
    # PostgreSQL cannot drop an enum value, so the type is rebuilt. Log rows
    # with the two removed actions go back to the actions they were stored
    # under before this migration.
    op.execute("ALTER TABLE audit_logs ALTER COLUMN action TYPE text USING action::text")
    op.execute("UPDATE audit_logs SET action = 'TICKET_VENDOR_ASSIGNED' WHERE action = 'VENDOR_CREATED'")
    op.execute("UPDATE audit_logs SET action = 'SITE_SCHEDULE_UPDATED' WHERE action = 'SITE_CREATED'")
    op.execute("DROP TYPE audit_action")
    labels = ", ".join(f"'{label}'" for label in OLD_LABELS)
    op.execute(f"CREATE TYPE audit_action AS ENUM ({labels})")
    op.execute("ALTER TABLE audit_logs ALTER COLUMN action TYPE audit_action USING action::audit_action")