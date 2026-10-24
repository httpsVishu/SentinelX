"""Typed contracts for what each of the seven agents produces.

Used by the agents to build their output, and as the documented shape stored
in AgentExecution.output_snapshot. Kept apart from the ORM models so agents
stay testable with plain data.
"""
import uuid
from typing import Any

from pydantic import BaseModel


class ReconOutput(BaseModel):
    technology_stack: list[str]
    discovered_endpoints: list[str]
    exposed_services: list[str]
    excluded_paths_respected: list[str]
    summary: str


class MappingOutput(BaseModel):
    attack_surface_endpoints: list[str]
    input_points: list[str]
    authentication_boundaries: list[str]
    apis: list[str]
    summary: str


class RawScannerFinding(BaseModel):
    """Normalized shape every scanner adapter (Nuclei, ZAP, Nmap, Mock) produces."""

    source_tool: str  # "nuclei" | "zap" | "nmap" | "mock"
    title: str
    description: str
    severity_hint: str  # the tool's own label, normalized downstream
    affected_endpoint: str
    raw_output: dict[str, Any]


class AssessmentOutput(BaseModel):
    raw_findings: list[RawScannerFinding]
    tools_invoked: list[str]
    # One entry per tool that failed. A verification re-scan with any entry
    # here cannot pass, because a failed tool proves nothing about the fix.
    tool_errors: list[str] = []
    summary: str


class ValidatedFinding(BaseModel):
    raw_finding_index: int  # index into AssessmentOutput.raw_findings
    verdict: str  # confirmed | discarded | inconclusive | needs_manual_review
    confidence: float
    poc_summary: str | None
    severity: str  # Severity value, normalized by the Validation Agent


class ValidationOutput(BaseModel):
    validated_findings: list[ValidatedFinding]
    summary: str


class ReportingOutput(BaseModel):
    finding_id: uuid.UUID
    title: str
    plain_language_report: str
    remediation_guidance: str
    references: list[str] = []


class AccountabilityOutput(BaseModel):
    finding_id: uuid.UUID
    suggested_vendor_id: uuid.UUID | None
    suggested_deadline_days: int
    vendor_mapped: bool


class VerificationOutput(BaseModel):
    ticket_id: uuid.UUID
    # passed | failed | inconclusive. Only passed and failed change the ticket.
    result: str
    notes: str | None