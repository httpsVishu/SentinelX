"""Pydantic schemas for the computed Vendor Scorecard."""
import uuid

from pydantic import BaseModel


class VendorScorecardRead(BaseModel):
    vendor_id: uuid.UUID
    vendor_name: str
    fix_rate: float  # verified-closed tickets / total terminal tickets, 0.0-1.0
    avg_response_time_hours: float | None  # avg time from ticket creation to first remediation submission
    missed_deadlines: int
    repeat_vulnerabilities: int  # findings on the same site+endpoint recurring after a prior verified close
    verified_ticket_count: int
    overdue_ticket_count: int
    total_ticket_count: int


class VendorScorecardExportRequest(BaseModel):
    """Placeholder body for POST /scorecards/{vendor_id}/export — MVP export
    is a synchronous CSV/JSON response, no async job needed at this scale."""
    format: str = "json"  # "json" or "csv"