"""Pydantic schemas for Ticket, RemediationSubmission, and VerificationRecord.

Two distinct read schemas are provided for a ticket: TicketRead (Admin
facing, full detail) and VendorTicketRead (used by /tickets/mine routes),
which never surfaces raw_scanner_output or the full PoC detail, only what
SRS 4.4-2 says a Vendor should see ("Sensitive exploit detail shall be shown
only to the extent needed to fix the issue").
"""
import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import DeadlineSource, Severity, TicketStatus, VerificationResult


class TicketAssignUpdate(BaseModel):
    """Admin reviewing the Accountability Agent's suggested vendor/deadline
    (SRS 4.3-4): accept as-is, or override vendor and/or deadline with a
    reason."""

    vendor_id: uuid.UUID | None = None
    deadline_override: datetime | None = None
    override_reason: str | None = Field(default=None, max_length=2000)


class RemediationSubmissionCreate(BaseModel):
    note: str = Field(min_length=1, max_length=4000)


class RemediationSubmissionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    ticket_id: uuid.UUID
    vendor_user_id: uuid.UUID
    note: str
    submitted_at: datetime


class VerificationRecordRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    ticket_id: uuid.UUID
    scan_id: uuid.UUID
    result: VerificationResult
    notes: str | None
    verified_at: datetime


class TicketRead(BaseModel):
    """Admin-facing ticket detail."""
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    finding_id: uuid.UUID
    site_id: uuid.UUID
    vendor_id: uuid.UUID | None
    severity: Severity
    status: TicketStatus
    deadline: datetime
    suggested_deadline: datetime
    deadline_source: DeadlineSource
    override_reason: str | None
    created_at: datetime
    closed_at: datetime | None
    remediation_submissions: list[RemediationSubmissionRead] = []
    verification_records: list[VerificationRecordRead] = []


class VendorTicketRead(BaseModel):
    """Vendor-facing ticket detail. No raw scanner output and no internal
    override rationale."""
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    site_id: uuid.UUID
    # Vendors cannot call the Admin-only sites API, so the name comes with the ticket.
    site_name: str | None = None
    severity: Severity
    status: TicketStatus
    deadline: datetime
    created_at: datetime
    # Taken from the linked Finding's plain-language fields only, never
    # raw_scanner_output or poc_summary.
    plain_language_report: str | None = None
    remediation_guidance: str | None = None
    affected_endpoint: str | None = None
    remediation_submissions: list[RemediationSubmissionRead] = []


class TicketListItem(BaseModel):
    """Lightweight row shape for ticket list and table views."""
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    site_id: uuid.UUID
    vendor_id: uuid.UUID | None
    severity: Severity
    status: TicketStatus
    deadline: datetime
    created_at: datetime