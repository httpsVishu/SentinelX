"""LLM provider factory — resolves the configured provider per agent group,
and is the single enforcement point for the safety rule that early agents
(which handle raw live-target scan data) may never be routed to the hosted
Claude provider.
"""
from app.config import LLMMode, settings
from app.llm.base import LLMProvider
from app.llm.claude_provider import ClaudeProvider
from app.llm.mock_provider import MockProvider
from app.llm.self_hosted_provider import SelfHostedProvider


class UnsafeLLMConfigurationError(Exception):
    """Raised at startup if EARLY_AGENT_LLM_MODE is misconfigured to use
    Claude, which would send raw live-target scan data to a hosted API."""


def _build_provider(mode: LLMMode) -> LLMProvider:
    if mode == LLMMode.MOCK:
        return MockProvider()
    if mode == LLMMode.SELF_HOSTED:
        return SelfHostedProvider()
    if mode == LLMMode.CLAUDE:
        return ClaudeProvider()
    raise ValueError(f"Unknown LLM mode: {mode}")


def get_early_agent_llm_provider() -> LLMProvider:
    """Provider for Recon, Mapping, Assessment, Validation. Hard-blocked
    from ever being Claude — raw scan data must stay on self-hosted/mock
    infrastructure, per the SRS design constraint."""
    if settings.EARLY_AGENT_LLM_MODE == LLMMode.CLAUDE:
        raise UnsafeLLMConfigurationError(
            "EARLY_AGENT_LLM_MODE is set to 'claude', but early agents process raw "
            "live-target scan data, which must not be sent to a hosted LLM API. "
            "Set EARLY_AGENT_LLM_MODE to 'mock' or 'self_hosted'."
        )
    return _build_provider(settings.EARLY_AGENT_LLM_MODE)


def get_late_agent_llm_provider() -> LLMProvider:
    """Provider for Reporting, Accountability, Verification — may safely
    use mock, self_hosted, or claude, since these stages only ever receive
    already-confirmed, human-approved finding data."""
    return _build_provider(settings.LATE_AGENT_LLM_MODE)