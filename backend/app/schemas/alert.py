"""Pydantic schemas for Alert resources."""
import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.enums import AlertDeliveryStatus, AlertLevel, AlertTriggerType


class AlertRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    trigger_type: AlertTriggerType
    level: AlertLevel
    site_id: uuid.UUID | None
    ticket_id: uuid.UUID | None
    finding_id: uuid.UUID | None
    recipient_user_id: uuid.UUID
    message: str
    delivery_status: AlertDeliveryStatus
    delivery_channel: str | None
    delivery_error: str | None
    created_at: datetime
    delivered_at: datetime | None


class AlertFilterParams(BaseModel):
    """Query params for GET /alerts (Alert & Notification Centre filters:
    filterable by site, severity/level, and type per SRS 3.1)."""
    site_id: uuid.UUID | None = None
    level: AlertLevel | None = None
    trigger_type: AlertTriggerType | None = None