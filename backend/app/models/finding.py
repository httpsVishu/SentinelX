"""Finding — a single potential vulnerability discovered on a Site, plus its
review by a Department Admin.

Sensitive columns (raw_scanner_output, poc_summary) are encrypted at rest
using pgcrypto (see app/core/crypto.py for the encrypt/decrypt helpers used
by app/services/finding_service.py — encryption is applied at the
application layer via pgcrypto SQL functions rather than transparent column
encryption, keeping the ORM model itself simple: these fields are stored as
`bytea` and only ever read/written through the service layer).

FindingReview captures the Admin's Approve/Reject decision separately from
the Finding row itself, per SRS 4.3-3's requirement that the decision be
recorded with the Admin's name and the time, and support the "Request More
Evidence" alternate flow (re-review is just another Finding status cycle
back through Validation, with a new FindingReview possible on the next
review round).
"""
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, LargeBinary, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.enums import FindingStatus, ReviewDecision, Severity


class Finding(Base):
    __tablename__ = "findings"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    site_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sites.id", ondelete="CASCADE"), nullable=False, index=True
    )
    scan_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("scans.id", ondelete="CASCADE"), nullable=False, index=True
    )

    title: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    severity: Mapped[Severity] = mapped_column(
        Enum(Severity, name="severity"), nullable=False, index=True
    )
    # OWASP Top 10 category, where applicable (SRS 3.5.1). Free text since
    # not every finding maps cleanly to a fixed OWASP category.
    owasp_category: Mapped[str | None] = mapped_column(String(255), nullable=True)

    confidence: Mapped[float] = mapped_column(Numeric(4, 3), nullable=False, default=0.0)
    affected_endpoint: Mapped[str] = mapped_column(String(2048), nullable=False)

    status: Mapped[FindingStatus] = mapped_column(
        Enum(FindingStatus, name="finding_status"),
        nullable=False,
        default=FindingStatus.RAW,
        index=True,
    )

    # ---- Sensitive / pgcrypto-encrypted columns ----
    # Raw scanner tool output (Nuclei/ZAP/Nmap JSON), retained for
    # traceability per SRS 3.4, but never surfaced to Vendors or in
    # notifications.
    raw_scanner_output_encrypted: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    # Plain-language, non-destructive PoC summary produced by the Validation
    # Agent. Encrypted since it may still describe how a flaw was confirmed.
    poc_summary_encrypted: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)

    # Reporting Agent's plain-language report (not raw exploit detail) —
    # not sensitive in the same way, kept in plaintext for easy display.
    plain_language_report: Mapped[str | None] = mapped_column(Text, nullable=True)
    remediation_guidance: Mapped[str | None] = mapped_column(Text, nullable=True)

    validated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    # ---- Relationships ----
    site: Mapped["Site"] = relationship(back_populates="findings")  # noqa: F821
    scan: Mapped["Scan"] = relationship(back_populates="findings")  # noqa: F821
    reviews: Mapped[list["FindingReview"]] = relationship(  # noqa: F821
        back_populates="finding", cascade="all, delete-orphan", order_by="FindingReview.decided_at"
    )
    ticket: Mapped["Ticket | None"] = relationship(back_populates="finding", uselist=False)  # noqa: F821

    def __repr__(self) -> str:
        return f"<Finding id={self.id} title={self.title!r} status={self.status}>"


class FindingReview(Base):
    __tablename__ = "finding_reviews"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    finding_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("findings.id", ondelete="CASCADE"), nullable=False, index=True
    )
    reviewer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )

    decision: Mapped[ReviewDecision] = mapped_column(
        Enum(ReviewDecision, name="review_decision"), nullable=False
    )
    # Required when decision == REJECT (enforced in the service layer, not
    # the DB, so a single column can serve both decision types).
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    decided_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # ---- Relationships ----
    finding: Mapped["Finding"] = relationship(back_populates="reviews")  # noqa: F821
    reviewer: Mapped["User"] = relationship()  # noqa: F821

    def __repr__(self) -> str:
        return f"<FindingReview id={self.id} finding_id={self.finding_id} decision={self.decision}>"