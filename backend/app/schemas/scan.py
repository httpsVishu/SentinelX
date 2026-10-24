"""Pydantic schemas for Scan and AgentExecution resources."""
import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.enums import AgentExecutionStatus, AgentName, ScanStatus, ScanTriggerType


class ScanTriggerRequest(BaseModel):
    """Body for POST /scans/{site_id}/trigger — manual on-demand scan."""
    note: str | None = None


class ScanRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    site_id: uuid.UUID
    trigger_type: ScanTriggerType
    status: ScanStatus
    target_scope: list[str] | None
    verification_ticket_id: uuid.UUID | None
    triggered_by_user_id: uuid.UUID | None
    error_message: str | None
    queued_at: datetime
    started_at: datetime | None
    completed_at: datetime | None


class AgentExecutionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    scan_id: uuid.UUID
    agent_name: AgentName
    status: AgentExecutionStatus
    input_snapshot: dict
    output_snapshot: dict | None
    error_message: str | None
    started_at: datetime
    completed_at: datetime | None