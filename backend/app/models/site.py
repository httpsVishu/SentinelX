"""Site — a registered target website/application under SentinelX
monitoring.

Implementation assumption (stated in Phase 1, item 1): a site does NOT need
a vendor mapped before scanning is enabled — only before an approved
finding can be turned into an assigned ticket (handled by the Accountability
Agent / TicketService, which falls back to TicketStatus.UNASSIGNED when
vendor_id is None). Vendor mapping IS required, per the SRS's site
adaptation requirements, as an optional but expected configuration field.

Target safety (SRS 2.5 / 3.2 / IT Act 2000): if `is_gov_in` is true, a scan
must not be permitted unless a linked, non-revoked AuthorizationRecord
exists. This check lives in app/services/authorization_service.py and is
invoked before every scan trigger, not just enforced here at the model
level.
"""
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Site(Base):
    __tablename__ = "sites"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    department_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("departments.id", ondelete="CASCADE"), nullable=False, index=True
    )

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    url: Mapped[str] = mapped_column(String(2048), nullable=False)

    # Nullable until the Admin maps a responsible vendor. Scanning is still
    # permitted (see module docstring); ticket assignment is not, until set.
    vendor_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("vendors.id", ondelete="SET NULL"), nullable=True, index=True
    )

    # Scan frequency in days (e.g. 7 = weekly). Kept as a plain integer
    # rather than a cron string to keep the MVP's Celery Beat logic simple.
    scan_frequency_days: Mapped[int] = mapped_column(Integer, nullable=False, default=7)

    excluded_paths: Mapped[list[str]] = mapped_column(
        ARRAY(String(1024)), nullable=False, default=list, server_default="{}"
    )

    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)  # False = paused
    is_gov_in: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
    last_scanned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # ---- Relationships ----
    department: Mapped["Department"] = relationship(back_populates="sites")  # noqa: F821
    vendor: Mapped["Vendor | None"] = relationship(back_populates="sites")  # noqa: F821
    scans: Mapped[list["Scan"]] = relationship(  # noqa: F821
        back_populates="site", cascade="all, delete-orphan"
    )
    findings: Mapped[list["Finding"]] = relationship(  # noqa: F821
        back_populates="site", cascade="all, delete-orphan"
    )
    tickets: Mapped[list["Ticket"]] = relationship(back_populates="site")  # noqa: F821
    authorization_records: Mapped[list["AuthorizationRecord"]] = relationship(  # noqa: F821
        back_populates="site", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Site id={self.id} name={self.name!r} url={self.url!r}>"