"""ReconAgent — inspects the authorized target, identifies technology
information, and enumerates endpoints/exposed services safely.

Per SRS 3.2/19: must not perform destructive exploitation. This agent only
ever makes standard, read-only HTTP(S) requests (GET/HEAD) the same way a
browser would — no fuzzing, no authentication bypass attempts, no payload
injection. Excluded paths are filtered out of the discovered endpoint list
before being handed to downstream agents.
"""
import uuid
from typing import Any
from urllib.parse import urljoin

import httpx

from app.agents.base_agent import BaseAgent
from app.llm import get_early_agent_llm_provider
from app.models.enums import AgentName
from app.schemas.agent import ReconOutput

_SYSTEM_PROMPT = (
    "You are the Recon stage of SentinelX's vulnerability management pipeline. "
    "Given raw HTTP response headers and a short list of discovered links for an "
    "authorized target, summarize the apparent technology stack, exposed "
    "services, and discovered endpoints in a safe, factual, non-speculative way. "
    "Respond ONLY with JSON matching the ReconOutput schema: "
    '{"technology_stack": [...], "discovered_endpoints": [...], '
    '"exposed_services": [...], "excluded_paths_respected": [...], "summary": "..."}'
)

# A small, fixed set of common, harmless paths used to seed discovery. A
# real implementation might also crawl links found in the homepage; kept
# minimal here to stay strictly read-only and avoid anything resembling a
# directory brute-force.
_COMMON_PATHS = ["/", "/robots.txt", "/sitemap.xml", "/api", "/login"]


class ReconAgent(BaseAgent):
    agent_name = AgentName.RECON

    def _fetch_headers_and_links(self, target_url: str, excluded_paths: list[str]) -> dict[str, Any]:
        headers_by_path: dict[str, dict[str, str]] = {}
        reachable_paths: list[str] = []

        with httpx.Client(timeout=15, follow_redirects=True) as client:
            for path in _COMMON_PATHS:
                if any(path.startswith(p) for p in excluded_paths):
                    continue
                url = urljoin(target_url, path)
                try:
                    resp = client.get(url)
                    headers_by_path[path] = dict(resp.headers)
                    if resp.status_code < 400:
                        reachable_paths.append(path)
                except httpx.HTTPError:
                    continue  # unreachable path is not an error for recon purposes

        return {"headers_by_path": headers_by_path, "reachable_paths": reachable_paths}

    def _execute(self, scan_id: uuid.UUID, input_data: dict[str, Any]) -> dict[str, Any]:
        target_url = input_data["target_url"]
        excluded_paths = input_data.get("excluded_paths", [])

        raw_recon = self._fetch_headers_and_links(target_url, excluded_paths)

        provider = get_early_agent_llm_provider()
        user_prompt = (
            f"Target: {target_url}\n"
            f"Excluded paths (must not appear in discovered_endpoints): {excluded_paths}\n"
            f"Raw HTTP headers observed per path: {raw_recon['headers_by_path']}\n"
            f"Reachable paths: {raw_recon['reachable_paths']}"
        )
        structured = provider.complete_structured(_SYSTEM_PROMPT, user_prompt)

        output = ReconOutput(
            technology_stack=structured.get("technology_stack", []),
            discovered_endpoints=[
                e for e in structured.get("discovered_endpoints", raw_recon["reachable_paths"])
                if not any(e.startswith(p) for p in excluded_paths)
            ],
            exposed_services=structured.get("exposed_services", []),
            excluded_paths_respected=excluded_paths,
            summary=structured.get("summary", "Reconnaissance completed."),
        )
        return output.model_dump(mode="json")
