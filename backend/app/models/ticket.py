"""Ticket: links one Admin-approved Finding to the Vendor responsible for
fixing it, with an SLA deadline that is fixed at creation time and never
silently recalculated.

RemediationSubmission and VerificationRecord are separate tables because a
ticket can be reported fixed and verified more than once (Fix Failed, then
Reopened, then Fix Submitted again, then Verified), and each attempt needs its
own timestamped record for the audit trail and the scorecard.
"""
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.enums import DeadlineSource, Severity, TicketStatus, VerificationResult


class Ticket(Base):
    __tablename__ = "tickets"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    finding_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("findings.id", ondelete="RESTRICT"), nullable=False, unique=True
    )
    site_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sites.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    # Null only while status is UNASSIGNED (SRS 4.5-3 A1: no vendor mapped yet).
    vendor_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("vendors.id", ondelete="RESTRICT"), nullable=True, index=True
    )

    severity: Mapped[Severity] = mapped_column(Enum(Severity, name="ticket_severity"), nullable=False)
    status: Mapped[TicketStatus] = mapped_column(
        Enum(TicketStatus, name="ticket_status"),
        nullable=False,
        default=TicketStatus.UNASSIGNED,
        index=True,
    )

    # Resolved and stored at creation time (see app/core/sla.py). Not
    # recalculated if the SLA settings change later.
    deadline: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    # What the SLA formula suggested, kept even when overridden, so the
    # override is traceable against the original.
    suggested_deadline: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    deadline_source: Mapped[DeadlineSource] = mapped_column(
        Enum(DeadlineSource, name="deadline_source"), nullable=False, default=DeadlineSource.AUTO
    )
    override_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Set once, when the daily check first marks the ticket OVERDUE. It stays
    # set when the ticket later moves on, so the scorecard still counts the miss.
    became_overdue_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # ---- Relationships ----
    finding: Mapped["Finding"] = relationship(back_populates="ticket")  # noqa: F821
    site: Mapped["Site"] = relationship(back_populates="tickets")  # noqa: F821
    vendor: Mapped["Vendor | None"] = relationship(back_populates="tickets")  # noqa: F821
    remediation_submissions: Mapped[list["RemediationSubmission"]] = relationship(
        back_populates="ticket", cascade="all, delete-orphan", order_by="RemediationSubmission.submitted_at"
    )
    verification_records: Mapped[list["VerificationRecord"]] = relationship(
        back_populates="ticket", cascade="all, delete-orphan", order_by="VerificationRecord.verified_at"
    )

    def __repr__(self) -> str:
        return f"<Ticket id={self.id} status={self.status} vendor_id={self.vendor_id}>"


class RemediationSubmission(Base):
    __tablename__ = "remediation_submissions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    ticket_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tickets.id", ondelete="CASCADE"), nullable=False, index=True
    )
    vendor_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    note: Mapped[str] = mapped_column(Text, nullable=False)
    submitted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    ticket: Mapped["Ticket"] = relationship(back_populates="remediation_submissions")
    vendor_user: Mapped["User"] = relationship()  # noqa: F821

    def __repr__(self) -> str:
        return f"<RemediationSubmission id={self.id} ticket_id={self.ticket_id}>"


class VerificationRecord(Base):
    __tablename__ = "verification_records"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    ticket_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tickets.id", ondelete="CASCADE"), nullable=False, index=True
    )
    scan_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("scans.id", ondelete="RESTRICT"), nullable=False
    )
    result: Mapped[VerificationResult] = mapped_column(
        Enum(VerificationResult, name="verification_result"), nullable=False
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    verified_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    ticket: Mapped["Ticket"] = relationship(back_populates="verification_records")
    scan: Mapped["Scan"] = relationship()  # noqa: F821

    def __repr__(self) -> str:
        return f"<VerificationRecord id={self.id} ticket_id={self.ticket_id} result={self.result}>"