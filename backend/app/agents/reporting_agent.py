"""ReportingAgent — generates a clear plain-language vulnerability report
for an already-confirmed, already-Admin-approved Finding.

Uses the LATE-agent LLM provider (may be Claude), since by this stage the
finding has already been through human sign-off and this agent only
receives the already-stored Finding fields — never raw_scanner_output,
which stays encrypted and is never passed into this agent's prompt.
"""
import uuid
from typing import Any

from app.agents.base_agent import BaseAgent
from app.llm import get_late_agent_llm_provider
from app.models.enums import AgentName
from app.schemas.agent import ReportingOutput

_SYSTEM_PROMPT = (
    "You are the Reporting stage of SentinelX's vulnerability management "
    "pipeline. You are given a CONFIRMED, Admin-APPROVED finding's title, "
    "severity, affected endpoint, and a safe PoC summary (no raw exploit "
    "detail). Write a clear, plain-language report and concrete remediation "
    "guidance suitable for a vendor who needs to fix it — do not include any "
    "raw exploit payload or step-by-step exploitation instructions. Respond "
    "ONLY with JSON matching: "
    '{"plain_language_report": "...", "remediation_guidance": "...", '
    '"references": [...]}'
)


class ReportingAgent(BaseAgent):
    agent_name = AgentName.REPORTING

    def _execute(self, scan_id: uuid.UUID, input_data: dict[str, Any]) -> dict[str, Any]:
        finding_id = uuid.UUID(input_data["finding_id"])
        title = input_data["title"]
        severity = input_data["severity"]
        affected_endpoint = input_data["affected_endpoint"]
        poc_summary = input_data.get("poc_summary", "")

        provider = get_late_agent_llm_provider()
        user_prompt = (
            f'title="{title}"\nseverity={severity}\naffected_endpoint={affected_endpoint}\n'
            f"safe_poc_summary={poc_summary}"
        )
        structured = provider.complete_structured(_SYSTEM_PROMPT, user_prompt)

        output = ReportingOutput(
            finding_id=finding_id,
            title=title,
            plain_language_report=structured.get("plain_language_report", ""),
            remediation_guidance=structured.get("remediation_guidance", ""),
            references=structured.get("references", []),
        )
        return output.model_dump(mode="json")