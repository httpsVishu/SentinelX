"""Add the ticket assignment alert kinds

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-11 17:00:00 UTC

Adds TICKET_ASSIGNED and TICKET_DEADLINE_CHANGED to the alert_trigger_type
enum. Labels are the Python member NAMES, as in the initial migration.
"""
from collections.abc import Sequence

from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

NEW_LABELS = ("TICKET_ASSIGNED", "TICKET_DEADLINE_CHANGED")

OLD_LABELS = (
    "CRITICAL_FINDING_CONFIRMED", "HIGH_FINDING_CONFIRMED", "UNAUTHORIZED_CHANGE",
    "DEADLINE_MISSED", "VERIFICATION_FAILED", "SCAN_FAILED", "PIPELINE_FAILURE",
)


def upgrade() -> None:
    # On older PostgreSQL versions a new enum value cannot be added inside a
    # transaction block, so this step runs outside the migration's transaction.
    with op.get_context().autocommit_block():
        for label in NEW_LABELS:
            op.execute(f"ALTER TYPE alert_trigger_type ADD VALUE IF NOT EXISTS '{label}'")


def downgrade() -> None:
    # PostgreSQL cannot drop an enum value, so the type is rebuilt. Alerts of
    # the two removed kinds are deleted first, because they cannot be stored
    # under the old type.
    op.execute("DELETE FROM alerts WHERE trigger_type IN ('TICKET_ASSIGNED', 'TICKET_DEADLINE_CHANGED')")
    op.execute("ALTER TYPE alert_trigger_type RENAME TO alert_trigger_type_old")
    labels = ", ".join(f"'{label}'" for label in OLD_LABELS)
    op.execute(f"CREATE TYPE alert_trigger_type AS ENUM ({labels})")
    op.execute(
        "ALTER TABLE alerts ALTER COLUMN trigger_type TYPE alert_trigger_type "
        "USING trigger_type::text::alert_trigger_type"
    )
    op.execute("DROP TYPE alert_trigger_type_old")