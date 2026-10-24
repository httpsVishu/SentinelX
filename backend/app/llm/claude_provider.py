"""ClaudeProvider — wraps the Anthropic API for the later, non-raw-data
agents (Reporting, Accountability, Verification).

Must only ever be used on already-confirmed, already-human-approved finding
data — never on raw scanner output from a live target. This file does not
enforce that itself (it has no knowledge of what data it's given); the
enforcement is structural, in app/llm/__init__.py's provider factory, which
refuses to let EARLY_AGENT_LLM_MODE be set to "claude" at all.
"""
from anthropic import Anthropic, APIError

from app.config import settings
from app.llm.base import LLMError, LLMProvider


class ClaudeProvider(LLMProvider):
    name = "claude"

    def __init__(self) -> None:
        if not settings.ANTHROPIC_API_KEY:
            raise LLMError(
                "ANTHROPIC_API_KEY is not set but LATE_AGENT_LLM_MODE=claude. "
                "Set the key or switch LATE_AGENT_LLM_MODE to mock/self_hosted."
            )
        self._client = Anthropic(api_key=settings.ANTHROPIC_API_KEY, timeout=settings.LLM_REQUEST_TIMEOUT_SECONDS)

    def complete(self, system_prompt: str, user_prompt: str, *, json_mode: bool = False) -> str:
        effective_system = system_prompt
        if json_mode:
            effective_system += "\n\nRespond with ONLY valid JSON, no prose, no markdown code fences."

        try:
            response = self._client.messages.create(
                model=settings.ANTHROPIC_MODEL_NAME,
                max_tokens=2000,
                system=effective_system,
                messages=[{"role": "user", "content": user_prompt}],
            )
        except APIError as exc:
            raise LLMError(f"Claude API request failed: {exc}") from exc

        text_blocks = [block.text for block in response.content if getattr(block, "type", None) == "text"]
        if not text_blocks:
            raise LLMError("Claude API returned no text content.")
        return "".join(text_blocks)