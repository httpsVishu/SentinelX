"""AccountabilityAgent — identifies the responsible vendor and calculates
the suggested SLA deadline for an approved finding, preparing ticket data.

This agent produces a *suggestion* (AccountabilityOutput); the actual
Ticket row creation is performed by
app/services/ticket_service.py::create_ticket_from_approved_finding(),
called by the orchestration layer right after this agent runs — keeping
"agent reasoning" and "database write with transactional guarantees"
cleanly separated, consistent with how Validation/Assessment are split from
their respective services.
"""
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents.base_agent import BaseAgent
from app.core.sla import days_for_severity, get_active_sla_config
from app.llm import get_late_agent_llm_provider
from app.models.enums import AgentName, Severity
from app.models.site import Site
from app.schemas.agent import AccountabilityOutput

_SYSTEM_PROMPT = (
    "You are the Accountability stage of SentinelX's vulnerability "
    "management pipeline. You are given a finding's severity and the "
    "suggested SLA day count already calculated by the system. Simply "
    "acknowledge the assignment in one short rationale sentence — you do "
    "not need to recalculate anything. Respond ONLY with JSON matching: "
    '{"rationale": "..."}'
)


class AccountabilityAgent(BaseAgent):
    agent_name = AgentName.ACCOUNTABILITY

    def __init__(self, db: Session):
        super().__init__(db)

    def _execute(self, scan_id: uuid.UUID, input_data: dict[str, Any]) -> dict[str, Any]:
        finding_id = uuid.UUID(input_data["finding_id"])
        site_id = uuid.UUID(input_data["site_id"])
        department_id = uuid.UUID(input_data["department_id"])
        severity = Severity(input_data["severity"])

        site = self.db.execute(select(Site).where(Site.id == site_id)).scalar_one()
        config = get_active_sla_config(self.db, department_id)
        suggested_days = days_for_severity(config, severity)

        provider = get_late_agent_llm_provider()
        user_prompt = f"severity={severity.value}\nsuggested_deadline_days={suggested_days}\nvendor_mapped={site.vendor_id is not None}"
        provider.complete_structured(_SYSTEM_PROMPT, user_prompt)  # rationale only, not used for logic

        output = AccountabilityOutput(
            finding_id=finding_id,
            suggested_vendor_id=site.vendor_id,
            suggested_deadline_days=suggested_days,
            vendor_mapped=site.vendor_id is not None,
        )
        return output.model_dump(mode="json")
