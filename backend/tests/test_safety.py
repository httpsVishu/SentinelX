"""Safety rules from the SRS that must hold whatever the configuration says."""
import pytest

from app.config import LLMMode, settings
from app.llm import UnsafeLLMConfigurationError, get_early_agent_llm_provider, get_late_agent_llm_provider
from app.llm.base import LLMError
from app.llm.mock_provider import MockProvider
from app.models.enums import FindingStatus
from app.orchestration.graph import run_post_approval_pipeline
from tests import factories
from tests.factories import POC_TEXT, RAW_OUTPUT_TEXT


class SpyProvider(MockProvider):
    """A mock model that remembers every prompt it was given."""

    def __init__(self):
        self.prompts: list[str] = []

    def complete(self, system_prompt, user_prompt, *, json_mode=False):
        self.prompts.append(system_prompt + "\n" + user_prompt)
        return super().complete(system_prompt, user_prompt, json_mode=json_mode)


def test_the_early_agents_can_never_be_pointed_at_the_hosted_model(monkeypatch):
    monkeypatch.setattr(settings, "EARLY_AGENT_LLM_MODE", LLMMode.CLAUDE)

    with pytest.raises(UnsafeLLMConfigurationError):
        get_early_agent_llm_provider()


@pytest.mark.parametrize("mode", [LLMMode.MOCK, LLMMode.SELF_HOSTED])
def test_the_early_agents_accept_the_mock_and_the_self_hosted_model(monkeypatch, mode):
    monkeypatch.setattr(settings, "EARLY_AGENT_LLM_MODE", mode)

    assert get_early_agent_llm_provider().name == mode.value


def test_the_hosted_model_needs_an_api_key(monkeypatch):
    monkeypatch.setattr(settings, "LATE_AGENT_LLM_MODE", LLMMode.CLAUDE)
    monkeypatch.setattr(settings, "ANTHROPIC_API_KEY", "")

    with pytest.raises(LLMError):
        get_late_agent_llm_provider()


def test_the_hosted_stages_never_see_raw_scanner_output(db, dept, vendor_a, monkeypatch):
    spy = SpyProvider()
    monkeypatch.setattr("app.agents.reporting_agent.get_late_agent_llm_provider", lambda: spy)
    monkeypatch.setattr("app.agents.accountability_agent.get_late_agent_llm_provider", lambda: spy)
    site = factories.make_site(db, dept, vendor=vendor_a)
    finding = factories.make_finding(db, site, status=FindingStatus.APPROVED)

    run_post_approval_pipeline(db, finding.scan_id, finding, dept.id)

    assert len(spy.prompts) == 2  # Reporting and Accountability, nothing else
    assert any(POC_TEXT in prompt for prompt in spy.prompts)  # the safe summary is meant to reach them
    assert all(RAW_OUTPUT_TEXT not in prompt for prompt in spy.prompts)


def test_the_mock_model_picks_its_answer_by_stage_not_by_words_in_scanner_text():
    system_prompt = "You are the Validation stage of SentinelX's vulnerability management pipeline."
    user_prompt = (
        "[0] tool=mock title='Reconnaissance data exposed' severity_hint='high' "
        "endpoint='/x' description='verification report mapping'"
    )

    result = MockProvider().complete_structured(system_prompt, user_prompt)

    assert [item["verdict"] for item in result["validated_findings"]] == ["confirmed"]