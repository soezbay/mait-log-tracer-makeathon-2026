"""KI:connect provider (KI:connect.nrw, the AI gateway of NRW universities).

KI:connect speaks the OpenAI chat-completions format (https://chat.kiconnect.nrw/app/api-docs), so it
reuses the Groq conversation code: tool calling, retries with retry-after, readable errors. Models are
"deployments" assigned to the key's user group: `LLM_MODEL` must be one of the names that
`GET /v1/models` returns (`uv run python scripts/ask.py --list-models`).
"""
from __future__ import annotations

from collections.abc import Callable
from typing import Any

from .base import ProviderError
from .groq import GroqProvider

DEFAULT_BASE_URL = "https://chat.kiconnect.nrw/api/v1"


class KIConnectProvider(GroqProvider):
    name = "kiconnect"
    label = "KI:connect"
    key_env = "KICONNECT_API_KEY"
    # Deployments sit on different upstream providers; not every one accepts an output-limit
    # parameter, and KI:connect's own limits are high, so none is sent.
    max_tokens_param = None

    def __init__(self, api_key: str | None, model: str | None, base_url: str | None = None,
                 client: Any | None = None, reasoning_effort: str | None = None,
                 sleep: Callable[[float], None] | None = None, require_model: bool = True):
        if require_model and not model:
            raise ProviderError(
                "LLM_MODEL is not set: KI:connect needs a deployment name. "
                "List the ones your key can use: uv run python scripts/ask.py --list-models"
            )
        if client is None:
            if not api_key:
                raise ProviderError("KICONNECT_API_KEY is not set (put it in backend/.env).")
            from openai import OpenAI  # imported lazily so the package is optional

            # max_retries=0: with_retries is the only retry layer (it honours retry-after).
            client = OpenAI(api_key=api_key, base_url=base_url or DEFAULT_BASE_URL,
                            max_retries=0, timeout=180)
        super().__init__(None, model or "", client=client, reasoning_effort=reasoning_effort,
                         sleep=sleep)

    def list_models(self) -> list[str]:
        """Deployment names the key may use (GET /v1/models)."""
        try:
            return sorted(m.id for m in self.client.models.list())
        except Exception as exc:
            status = getattr(exc, "status_code", None)
            raise ProviderError(
                f"KI:connect could not list models ({status or type(exc).__name__}): "
                f"{str(getattr(exc, 'message', None) or exc)[:200]}"
            ) from exc
