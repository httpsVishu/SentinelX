"""SLAConfig — department-wide, versioned deadline formula.

Implementation assumption (Phase 1, item 2): SLA configuration is a single
department-wide table rather than per-site, per SRS 4.5-3's "The deadline
formula shall be configurable by the Admin department-wide, rather than
fixed per site."

Versioned via effective_from so a Ticket can store the deadline that was
actually in effect when it was created (see app/models/ticket.py and
app/core/sla.py) without retroactively changing existing tickets if the
Admin later edits the formula — satisfying SRS 3.4's "if the deadline
formula is changed later, existing tickets will not have their deadlines
changed automatically."
"""
import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class SLAConfig(Base):
    __tablename__ = "sla_configs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    department_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("departments.id", ondelete="CASCADE"), nullable=False, index=True
    )

    critical_days: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    high_days: Mapped[int] = mapped_column(Integer, nullable=False, default=7)
    medium_days: Mapped[int] = mapped_column(Integer, nullable=False, default=15)
    low_days: Mapped[int] = mapped_column(Integer, nullable=False, default=30)

    # When this configuration version took effect. The "current" config for
    # a department is the row with the most recent effective_from that is
    # not in the future — see app/core/sla.py::get_active_sla_config().
    effective_from: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # ---- Relationships ----
    department: Mapped["Department"] = relationship(back_populates="sla_configs")  # noqa: F821

    def __repr__(self) -> str:
        return (
            f"<SLAConfig id={self.id} dept={self.department_id} "
            f"C={self.critical_days} H={self.high_days} M={self.medium_days} L={self.low_days}>"
        )