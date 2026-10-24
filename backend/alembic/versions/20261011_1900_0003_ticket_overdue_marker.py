"""Record when a ticket first went overdue

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-11 19:00:00 UTC

Adds tickets.became_overdue_at. The scorecard counts a missed deadline from
this column, so a ticket that went overdue and was later reopened, fixed late
or closed is still counted. Tickets that are overdue right now are given their
deadline as the best available date.
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("tickets", sa.Column("became_overdue_at", sa.DateTime(timezone=True), nullable=True))
    op.execute("UPDATE tickets SET became_overdue_at = deadline WHERE status = 'OVERDUE'")


def downgrade() -> None:
    op.drop_column("tickets", "became_overdue_at")