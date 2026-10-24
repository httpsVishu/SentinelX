"""VerificationAgent: decides whether a claimed fix really worked.

The decision is deterministic and never comes from the language model:

  failed        the original issue is still confirmed on the endpoint
  inconclusive  the re-scan could not prove anything (a tool failed, no tool
                ran, or the original issue came back unresolved)
  passed        the re-scan ran cleanly and the original issue is gone

"Found nothing" only counts as fixed when the scan actually ran. An outage
must never close a ticket, per SRS 4.4-3. The model only writes the
human-readable notes for passed and failed.

The original issue is matched by title, so a different issue on the same
endpoint does not fail a correct fix. If no title is known, any confirmed
finding on the endpoint counts.

The ticket status change itself happens in
ticket_service.record_verification_result(), called by the orchestration
layer for passed and failed only.
"""
import uuid
from typing import Any

from app.agents.base_agent import BaseAgent
from app.llm import get_late_agent_llm_provider
from app.models.enums import AgentName
from app.schemas.agent import VerificationOutput

_SYSTEM_PROMPT = (
    "You are the Verification stage of SentinelX's vulnerability management "
    "pipeline. You are given the result of a targeted re-scan of a single "
    "endpoint that was previously confirmed vulnerable, and the decision the "
    "system already reached. Explain the decision in one or two plain "
    "sentences. Do not change the decision. "
    'Respond ONLY with JSON matching: {"result": "passed" or "failed", "notes": "..."}'
)


class VerificationAgent(BaseAgent):
    agent_name = AgentName.VERIFICATION

    def _execute(self, scan_id: uuid.UUID, input_data: dict[str, Any]) -> dict[str, Any]:
        ticket_id = uuid.UUID(input_data["ticket_id"])
        endpoint = input_data["affected_endpoint"]
        original_title = (input_data.get("original_title") or "").strip().lower()
        validated = input_data.get("validated_findings", [])
        raw_titles = input_data.get("raw_titles", [])
        tools_invoked = input_data.get("tools_invoked", [])
        tool_errors = input_data.get("tool_errors", [])

        def concerns_original(finding: dict[str, Any]) -> bool:
            if not original_title:
                return True
            index = finding.get("raw_finding_index")
            if not isinstance(index, int) or not (0 <= index < len(raw_titles)):
                return True  # cannot tell which issue this is, so be strict
            return str(raw_titles[index]).strip().lower() == original_title

        relevant = [f for f in validated if concerns_original(f)]
        still_present = any(f.get("verdict") == "confirmed" for f in relevant)
        unresolved = any(f.get("verdict") in ("inconclusive", "needs_manual_review") for f in relevant)

        if still_present:
            result, reason = "failed", f"The re-scan of {endpoint} still finds the issue."
        elif tool_errors or not tools_invoked:
            detail = "; ".join(tool_errors) if tool_errors else "no scanner ran"
            result, reason = "inconclusive", f"The re-scan of {endpoint} could not finish: {detail}."
        elif unresolved:
            result, reason = (
                "inconclusive",
                f"The re-scan of {endpoint} could not confirm whether the issue is gone.",
            )
        else:
            result, reason = "passed", f"The re-scan of {endpoint} no longer finds the issue."

        if result == "inconclusive":
            notes = reason  # no model call: nothing to explain beyond the reason
        else:
            provider = get_late_agent_llm_provider()
            user_prompt = (
                f"affected_endpoint={endpoint}\n"
                f"deterministic_result={result}\n"
                f"detail={reason}"
            )
            structured = provider.complete_structured(_SYSTEM_PROMPT, user_prompt)
            notes = structured.get("notes") or reason

        output = VerificationOutput(ticket_id=ticket_id, result=result, notes=notes)
        return output.model_dump(mode="json")