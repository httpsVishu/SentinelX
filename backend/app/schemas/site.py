"""Pydantic schemas for Site resources."""
import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


class SiteCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    url: str = Field(min_length=1, max_length=2048)
    vendor_id: uuid.UUID | None = None
    scan_frequency_days: int = Field(default=7, ge=1, le=365)
    excluded_paths: list[str] = Field(default_factory=list)
    is_gov_in: bool = False

    @field_validator("url")
    @classmethod
    def url_must_be_http(cls, v: str) -> str:
        if not (v.startswith("http://") or v.startswith("https://")):
            raise ValueError("url must start with http:// or https://")
        return v


class SiteUpdateSchedule(BaseModel):
    scan_frequency_days: int = Field(ge=1, le=365)


class SiteUpdateExclusions(BaseModel):
    excluded_paths: list[str]


class SiteUpdateVendor(BaseModel):
    vendor_id: uuid.UUID | None


class SiteUpdateActive(BaseModel):
    is_active: bool


class SiteRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    department_id: uuid.UUID
    name: str
    url: str
    vendor_id: uuid.UUID | None
    scan_frequency_days: int
    excluded_paths: list[str]
    is_active: bool
    is_gov_in: bool
    created_at: datetime
    last_scanned_at: datetime | None


class SiteSummary(BaseModel):
    """Lightweight shape for dashboard/portfolio listings — avoids pulling
    full nested relationships for a table row."""
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    url: str
    vendor_id: uuid.UUID | None
    is_active: bool
    last_scanned_at: datetime | None
    open_ticket_count: int = 0
    overdue_ticket_count: int = 0


class AuthorizationRecordCreate(BaseModel):
    document_reference: str = Field(min_length=1, max_length=512)
    notes: str | None = None
    granted_at: datetime


class AuthorizationRecordRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    site_id: uuid.UUID
    document_reference: str
    notes: str | None
    granted_by_user_id: uuid.UUID
    granted_at: datetime
    created_at: datetime