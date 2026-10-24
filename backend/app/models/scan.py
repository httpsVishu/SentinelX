"""Scan — one execution of the pipeline against a Site: either a full
scheduled/manual scan (Recon→Mapping→Assessment→Validation) or a narrow
verification scan (Assessment+Validation reused on a single endpoint).

Duplicate-run prevention (SRS 4.5-1 A2: "a scan for the same site is already
running... queued instead of run in parallel") is enforced in
app/services/scan_service.py by checking for an existing Scan with
status in (QUEUED, RUNNING) for the same site before creating a new one.
"""
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.enums import ScanStatus, ScanTriggerType


class Scan(Base):
    __tablename__ = "scans"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    site_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sites.id", ondelete="CASCADE"), nullable=False, index=True
    )

    trigger_type: Mapped[ScanTriggerType] = mapped_column(
        Enum(ScanTriggerType, name="scan_trigger_type"), nullable=False
    )
    status: Mapped[ScanStatus] = mapped_column(
        Enum(ScanStatus, name="scan_status"), nullable=False, default=ScanStatus.QUEUED, index=True
    )

    # For verification scans only: the specific endpoint(s) being re-checked,
    # rather than a full-site crawl. Empty/null for scheduled/manual scans,
    # which use the site's full scope minus excluded_paths.
    target_scope: Mapped[list[str] | None] = mapped_column(
        ARRAY(String(1024)), nullable=True
    )

    # Populated for verification scans: the ticket being verified.
    verification_ticket_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tickets.id", ondelete="SET NULL"), nullable=True
    )

    triggered_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    queued_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # ---- Relationships ----
    site: Mapped["Site"] = relationship(back_populates="scans")  # noqa: F821
    triggered_by: Mapped["User | None"] = relationship()  # noqa: F821
    agent_executions: Mapped[list["AgentExecution"]] = relationship(  # noqa: F821
        back_populates="scan", cascade="all, delete-orphan", order_by="AgentExecution.started_at"
    )
    findings: Mapped[list["Finding"]] = relationship(back_populates="scan")  # noqa: F821

    def __repr__(self) -> str:
        return f"<Scan id={self.id} site_id={self.site_id} status={self.status}>"