"""SelfHostedProvider — talks to a self-hosted, OpenAI-compatible LLM
endpoint (vLLM or TGI serving a Llama-3/Qwen2.5-class model).

Used for the early agents (Recon, Mapping, Assessment, Validation) that
handle raw live-target scan data, which per the SRS must stay inside the
department's own infrastructure rather than being sent to a hosted API.
"""
import httpx

from app.config import settings
from app.llm.base import LLMError, LLMProvider


class SelfHostedProvider(LLMProvider):
    name = "self_hosted"

    def __init__(self) -> None:
        self._client = httpx.Client(
            base_url=settings.SELF_HOSTED_LLM_BASE_URL,
            headers={"Authorization": f"Bearer {settings.SELF_HOSTED_LLM_API_KEY}"},
            timeout=settings.LLM_REQUEST_TIMEOUT_SECONDS,
        )

    def complete(self, system_prompt: str, user_prompt: str, *, json_mode: bool = False) -> str:
        payload = {
            "model": settings.SELF_HOSTED_LLM_MODEL_NAME,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.2,
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}

        try:
            resp = self._client.post("/chat/completions", json=payload)
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            raise LLMError(f"self-hosted LLM request failed: {exc}") from exc

        data = resp.json()
        try:
            return data["choices"][0]["message"]["content"]
        except (KeyError, IndexError) as exc:
            raise LLMError(f"self-hosted LLM returned an unexpected response shape: {data}") from exc

    def __del__(self) -> None:
        try:
            self._client.close()
        except Exception:  # noqa: BLE001
            pass