"""LLMProvider — the interface every language-model backend implements.

Used by all seven agents, but with a hard safety rule enforced in
app/llm/__init__.py's factory rather than here: Recon, Mapping, Assessment,
and Validation (the agents that handle raw live-target data) must never be
wired to the Claude provider, since raw scan data must not leave the
department's infrastructure. This file only defines the shared interface;
the routing rule lives in the factory so there's one place that decides
which concrete provider an agent gets.
"""
from abc import ABC, abstractmethod
from typing import Any


class LLMError(Exception):
    """Raised when a provider fails to produce a usable completion after
    its own internal retry/timeout handling."""


class LLMProvider(ABC):
    """Base interface for a text-completion backend."""

    name: str

    @abstractmethod
    def complete(self, system_prompt: str, user_prompt: str, *, json_mode: bool = False) -> str:
        """Return a text completion for the given prompts.

        If json_mode is True, the provider should instruct the underlying
        model to return valid JSON and the caller will attempt to parse the
        result — providers are not required to validate the JSON
        themselves, only to request it from the model.
        """
        raise NotImplementedError

    def complete_structured(self, system_prompt: str, user_prompt: str) -> dict[str, Any]:
        """Convenience wrapper: calls complete() in json_mode and parses
        the result. Raises LLMError if the response is not valid JSON."""
        import json

        raw = self.complete(system_prompt, user_prompt, json_mode=True)
        try:
            return json.loads(raw)
        except json.JSONDecodeError as exc:
            raise LLMError(f"{self.name} provider returned non-JSON output: {raw[:300]}") from exc