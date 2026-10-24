"""Pydantic schemas for Finding and FindingReview resources.

FindingRead decrypts and includes the proof summary for the Admin's Finding
Review screen (SRS 4.3-3). It must never be used for a Vendor-facing endpoint:
the vendor ticket schema in schemas/ticket.py has no proof or scanner fields.
FindingListItem is the light shape for list views and carries no proof at all.
"""
import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import FindingStatus, ReviewDecision, Severity


class FindingRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    site_id: uuid.UUID
    scan_id: uuid.UUID
    title: str
    description: str
    severity: Severity
    owasp_category: str | None
    confidence: float
    affected_endpoint: str
    status: FindingStatus
    poc_summary: str | None  # decrypted by the service layer before serialization
    plain_language_report: str | None
    remediation_guidance: str | None
    validated_at: datetime | None
    created_at: datetime


class FindingListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    site_id: uuid.UUID
    title: str
    severity: Severity
    status: FindingStatus
    affected_endpoint: str
    confidence: float
    created_at: datetime


class FindingReviewCreate(BaseModel):
    decision: ReviewDecision
    reason: str | None = Field(default=None, max_length=2000)


class FindingReviewRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    finding_id: uuid.UUID
    reviewer_id: uuid.UUID
    decision: ReviewDecision
    reason: str | None
    decided_at: datetime