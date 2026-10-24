"""Pydantic schemas for User resources."""
import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, field_validator

from app.models.enums import AlertTriggerType, UserRole

_KNOWN_ALERT_KINDS = {kind.value for kind in AlertTriggerType}


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    # Plain str on output: stored data is not re-validated when it is read back.
    email: str
    full_name: str
    role: UserRole
    is_active: bool
    department_id: uuid.UUID
    vendor_id: uuid.UUID | None
    muted_trigger_types: list[str]
    created_at: datetime
    last_login_at: datetime | None


class UserCreate(BaseModel):
    """Used by the Admin-only account-creation endpoint. Admins create Vendor
    accounts. There is no public self-registration in this MVP (Phase 1
    assumption 3). New addresses are validated, unlike stored ones."""

    email: EmailStr
    password: str
    full_name: str
    role: UserRole
    vendor_id: uuid.UUID | None = None


class UserUpdatePreferences(BaseModel):
    muted_trigger_types: list[str]

    @field_validator("muted_trigger_types")
    @classmethod
    def only_known_kinds(cls, value: list[str]) -> list[str]:
        unknown = sorted(set(value) - _KNOWN_ALERT_KINDS)
        if unknown:
            raise ValueError("Unknown alert kind: " + ", ".join(unknown)[:200])
        return sorted(set(value))