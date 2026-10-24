"""ValidationAgent — receives raw findings, performs only safe,
non-destructive validation, and classifies each as Confirmed, Discarded,
Inconclusive, or Needs Manual Review.

Hard safety rule (SRS 3.2/22): never runs a destructive, denial-of-service,
or data-exfiltrating payload, even to "prove" a finding is real, and never
blindly executes arbitrary payloads supplied by scanner output. This agent
performs no additional network requests of its own — "safe PoC" here means
LLM-reasoned plausibility assessment over the raw scanner evidence already
collected by the Assessment Agent (which itself only ran non-destructive
checks), not re-running or escalating any payload. A finding the model
judges would require an actually risky confirmation step (e.g. an
exploit requiring destructive follow-through to verify) is routed to
NEEDS_MANUAL_REVIEW rather than attempted.
"""
import uuid
from typing import Any

from app.agents.base_agent import BaseAgent
from app.llm import get_early_agent_llm_provider
from app.models.enums import AgentName
from app.scanners.normalizer import normalize_severity
from app.schemas.agent import ValidatedFinding, ValidationOutput

_SYSTEM_PROMPT = (
    "You are the Validation stage of SentinelX's vulnerability management "
    "pipeline. You are given a list of RAW scanner findings (already produced "
    "by non-destructive tools). For EACH finding, decide a verdict based only "
    "on the evidence given — you must NOT propose, describe, or simulate "
    "running any additional destructive, denial-of-service, data-exfiltrating, "
    "or credential-stealing test. If confirming a finding would require such a "
    "risky step, set its verdict to 'needs_manual_review' instead of "
    "'confirmed'. Possible verdicts: 'confirmed' (evidence is clear and "
    "safely attributable), 'discarded' (evidence does not actually support a "
    "real issue), 'inconclusive' (evidence is ambiguous), 'needs_manual_review' "
    "(would require a risky step to confirm further). For confirmed findings, "
    "write a short poc_summary describing in plain language why it's real, "
    "WITHOUT including exploit payload syntax. Respond ONLY with JSON matching: "
    '{"validated_findings": [{"raw_finding_index": int, "verdict": "...", '
    '"confidence": float, "poc_summary": "..." or null, "severity": "..."}], '
    '"summary": "..."}'
)


class ValidationAgent(BaseAgent):
    agent_name = AgentName.VALIDATION

    def _execute(self, scan_id: uuid.UUID, input_data: dict[str, Any]) -> dict[str, Any]:
        raw_findings = input_data.get("raw_findings", [])

        if not raw_findings:
            output = ValidationOutput(validated_findings=[], summary="No raw findings to validate.")
            return output.model_dump(mode="json")

        provider = get_early_agent_llm_provider()
        findings_description = "\n".join(
            f"[{i}] tool={f['source_tool']} title={f['title']!r} "
            f"severity_hint={f['severity_hint']!r} endpoint={f['affected_endpoint']!r} "
            f"description={f['description'][:300]!r}"
            for i, f in enumerate(raw_findings)
        )
        structured = provider.complete_structured(_SYSTEM_PROMPT, findings_description)

        validated: list[ValidatedFinding] = []
        for item in structured.get("validated_findings", []):
            idx = item.get("raw_finding_index")
            if idx is None or not (0 <= idx < len(raw_findings)):
                continue  # skip malformed entries rather than crashing the whole stage

            raw = raw_findings[idx]
            # Normalize severity server-side rather than trusting the LLM's
            # free-text severity verbatim, using the same mapping the
            # Assessment Agent's tools are known to use.
            normalized_severity = normalize_severity(raw["source_tool"], item.get("severity", raw["severity_hint"]))

            verdict = item.get("verdict", "inconclusive")
            if verdict not in ("confirmed", "discarded", "inconclusive", "needs_manual_review"):
                verdict = "inconclusive"

            validated.append(
                ValidatedFinding(
                    raw_finding_index=idx,
                    verdict=verdict,
                    confidence=float(item.get("confidence", 0.5)),
                    poc_summary=item.get("poc_summary") if verdict == "confirmed" else None,
                    severity=normalized_severity.value,
                )
            )

        output = ValidationOutput(
            validated_findings=validated,
            summary=structured.get("summary", f"Validated {len(validated)} of {len(raw_findings)} raw findings."),
        )
        return output.model_dump(mode="json")