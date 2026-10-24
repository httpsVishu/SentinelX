"""AssessmentAgent: runs Nuclei, ZAP and Nmap (or the MockScanner), collects
raw findings and normalizes them.

Also used for the Verification path with a narrowed scope_paths, so it always
respects excluded_paths and additionally restricts to scope_paths when given.
"""
import uuid
from typing import Any

from app.agents.base_agent import BaseAgent
from app.models.enums import AgentName
from app.scanners import get_scanner_adapters
from app.scanners.base import ScannerError
from app.schemas.agent import AssessmentOutput


class AssessmentAgent(BaseAgent):
    agent_name = AgentName.ASSESSMENT

    def _execute(self, scan_id: uuid.UUID, input_data: dict[str, Any]) -> dict[str, Any]:
        target_url = input_data["target_url"]
        excluded_paths = input_data.get("excluded_paths", [])
        scope_paths = input_data.get("scope_paths")

        all_findings = []
        tools_invoked: list[str] = []
        tool_errors: list[str] = []

        for adapter in get_scanner_adapters():
            try:
                all_findings.extend(adapter.scan(target_url, excluded_paths, scope_paths))
                tools_invoked.append(adapter.name)
            except ScannerError as exc:
                # One failing tool does not abort the assessment. The failure
                # is recorded so the Verification Agent can refuse to treat
                # "found nothing" as "fixed".
                tool_errors.append(f"{adapter.name}: {exc}")

        summary = f"Tools run: {', '.join(tools_invoked) or 'none'}. {len(all_findings)} raw finding(s)."
        if tool_errors:
            summary += f" Tool errors: {'; '.join(tool_errors)}"

        output = AssessmentOutput(
            raw_findings=all_findings,
            tools_invoked=tools_invoked,
            tool_errors=tool_errors,
            summary=summary,
        )
        return output.model_dump(mode="json")