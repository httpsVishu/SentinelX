"""PipelineState: the shared state passed between agents in a LangGraph run.

Stage outputs are stored as plain dicts (what BaseAgent.run returns), not as
the Pydantic output models. LangGraph validates the state schema every time it
hands state to a node. A model-typed field would quietly turn a dict into a
model object, which the next agent cannot read with .get() and which cannot
be stored as JSON in AgentExecution.input_snapshot.
"""
import uuid
from typing import Any

from pydantic import BaseModel, Field


class ScanPipelineState(BaseModel):
    """Recon -> Mapping -> Assessment -> Validation."""

    scan_id: uuid.UUID
    site_id: uuid.UUID
    target_url: str
    excluded_paths: list[str]
    scope_paths: list[str] | None = None

    recon_output: dict[str, Any] | None = None
    mapping_output: dict[str, Any] | None = None
    assessment_output: dict[str, Any] | None = None
    validation_output: dict[str, Any] | None = None

    errors: list[str] = Field(default_factory=list)


class PostApprovalPipelineState(BaseModel):
    """Reporting -> Accountability, run once a Finding is APPROVED."""

    finding_id: uuid.UUID
    site_id: uuid.UUID
    department_id: uuid.UUID

    reporting_output: dict[str, Any] | None = None
    accountability_output: dict[str, Any] | None = None

    errors: list[str] = Field(default_factory=list)


class VerificationPipelineState(BaseModel):
    """A narrow Assessment + Validation re-check of one ticket's endpoint,
    followed by the Verification Agent's decision."""

    scan_id: uuid.UUID
    ticket_id: uuid.UUID
    site_id: uuid.UUID
    target_url: str
    excluded_paths: list[str]
    affected_endpoint: str
    original_title: str | None = None

    assessment_output: dict[str, Any] | None = None
    validation_output: dict[str, Any] | None = None
    verification_output: dict[str, Any] | None = None

    errors: list[str] = Field(default_factory=list)


def model_to_dict(model: BaseModel) -> dict[str, Any]:
    """Helper for turning a Pydantic model into BaseAgent.run() input data."""
    return model.model_dump(mode="json")