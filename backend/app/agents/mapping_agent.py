"""MappingAgent — converts reconnaissance information into a structured
attack-surface representation for the Assessment Agent to work from.

Pure LLM-reasoning stage over already-collected recon data — makes no new
network requests itself.
"""
import uuid
from typing import Any

from app.agents.base_agent import BaseAgent
from app.llm import get_early_agent_llm_provider
from app.models.enums import AgentName
from app.schemas.agent import MappingOutput

_SYSTEM_PROMPT = (
    "You are the Mapping stage of SentinelX's vulnerability management pipeline. "
    "Given the Recon stage's output (technology stack, discovered endpoints, "
    "exposed services), produce a structured attack-surface map: which "
    "endpoints look like inputs, which look like authentication boundaries, "
    "and which look like APIs. Respond ONLY with JSON matching the "
    "MappingOutput schema: "
    '{"attack_surface_endpoints": [...], "input_points": [...], '
    '"authentication_boundaries": [...], "apis": [...], "summary": "..."}'
)


class MappingAgent(BaseAgent):
    agent_name = AgentName.MAPPING

    def _execute(self, scan_id: uuid.UUID, input_data: dict[str, Any]) -> dict[str, Any]:
        recon_output = input_data["recon_output"]

        provider = get_early_agent_llm_provider()
        user_prompt = (
            f"Technology stack: {recon_output.get('technology_stack', [])}\n"
            f"Discovered endpoints: {recon_output.get('discovered_endpoints', [])}\n"
            f"Exposed services: {recon_output.get('exposed_services', [])}\n"
            f"Recon summary: {recon_output.get('summary', '')}"
        )
        structured = provider.complete_structured(_SYSTEM_PROMPT, user_prompt)

        output = MappingOutput(
            attack_surface_endpoints=structured.get(
                "attack_surface_endpoints", recon_output.get("discovered_endpoints", [])
            ),
            input_points=structured.get("input_points", []),
            authentication_boundaries=structured.get("authentication_boundaries", []),
            apis=structured.get("apis", []),
            summary=structured.get("summary", "Attack-surface mapping completed."),
        )
        return output.model_dump(mode="json")