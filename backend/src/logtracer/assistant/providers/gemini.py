"""Gemini provider (google-genai SDK). Default for development: it has a free tier."""
from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from .base import (
    Conversation,
    LLMProvider,
    LLMResponse,
    ProviderError,
    ToolCall,
    ToolSpec,
    with_retries,
)

log = logging.getLogger(__name__)


def _gemini_schema(schema: Any) -> Any:
    """JSON-schema (lowercase types) -> Gemini Schema dict (uppercase types, supported keys only)."""
    if isinstance(schema, dict):
        out: dict[str, Any] = {}
        for k, v in schema.items():
            if k == "type" and isinstance(v, str):
                out[k] = v.upper()
            elif k in ("properties",):
                out[k] = {name: _gemini_schema(sub) for name, sub in v.items()}
            elif k == "items":
                out[k] = _gemini_schema(v)
            elif k in ("description", "required", "enum"):
                out[k] = v
        return out
    return schema


class GeminiProvider(LLMProvider):
    name = "gemini"

    def __init__(self, api_key: str | None, model: str, client: Any | None = None,
                 sleep: Callable[[float], None] | None = None):
        from google import genai  # imported lazily so the package is optional

        if client is None:
            if not api_key:
                raise ProviderError("GEMINI_API_KEY is not set (put it in backend/.env).")
            client = genai.Client(api_key=api_key)
        self.client = client
        self.model = model
        self._sleep = sleep

    def start(self, system: str, tools: list[ToolSpec], user_message: str) -> Conversation:
        return GeminiConversation(self, system, tools, user_message)


class GeminiConversation(Conversation):
    def __init__(self, provider: GeminiProvider, system: str, tools: list[ToolSpec], user_message: str):
        from google.genai import types

        self.types = types
        self.p = provider
        self.system = system
        self.tool_names = {t.name for t in tools}
        self.declarations = [
            types.FunctionDeclaration(name=t.name, description=t.description, parameters=_gemini_schema(t.parameters))
            for t in tools
        ]
        self.contents: list[Any] = [types.Content(role="user", parts=[types.Part(text=user_message)])]

    # ------------------------------------------------------------ helpers
    @staticmethod
    def _retryable(exc: Exception) -> bool:
        code = getattr(exc, "code", None)
        return code in (429, 500, 502, 503, 504)

    def _config(self, force_tool: str | None):
        t = self.types
        cfg: dict[str, Any] = {
            "system_instruction": self.system,
            "tools": [t.Tool(function_declarations=self.declarations)],
            "automatic_function_calling": t.AutomaticFunctionCallingConfig(disable=True),
        }
        if force_tool:
            cfg["tool_config"] = t.ToolConfig(
                function_calling_config=t.FunctionCallingConfig(mode="ANY", allowed_function_names=[force_tool])
            )
        return t.GenerateContentConfig(**cfg)

    # ------------------------------------------------------------ Conversation API
    def generate(self, force_tool: str | None = None) -> LLMResponse:
        config = self._config(force_tool)
        kwargs = {"sleep": self.p._sleep} if self.p._sleep else {}
        try:
            resp = with_retries(
                lambda: self.p.client.models.generate_content(
                    model=self.p.model, contents=self.contents, config=config
                ),
                self._retryable,
                **kwargs,
            )
        except Exception as exc:
            code = getattr(exc, "code", None)
            if code == 429:
                raise ProviderError("Gemini rate limit reached (free tier). Wait a minute and try again.") from exc
            if code in (400, 401, 403):
                raise ProviderError(f"Gemini rejected the request ({code}). Check GEMINI_API_KEY and LLM_MODEL.") from exc
            raise ProviderError(f"Gemini call failed: {type(exc).__name__}") from exc

        usage = getattr(resp, "usage_metadata", None)
        out = LLMResponse(
            input_tokens=getattr(usage, "prompt_token_count", 0) or 0,
            output_tokens=(getattr(usage, "candidates_token_count", 0) or 0)
            + (getattr(usage, "thoughts_token_count", 0) or 0),
        )
        candidates = getattr(resp, "candidates", None) or []
        content = candidates[0].content if candidates else None
        if content is None or not content.parts:
            # Blocked, empty or malformed call. The agent nudges the model; keep the history valid.
            reason = getattr(candidates[0], "finish_reason", None) if candidates else "no candidates"
            log.warning("Gemini returned no content (finish_reason=%s)", reason)
            return out
        self.contents.append(content)  # keep the raw content: Gemini needs its thought signatures back
        texts = []
        for part in content.parts:
            fc = getattr(part, "function_call", None)
            if fc is not None and fc.name:
                out.tool_calls.append(ToolCall(name=fc.name, args=dict(fc.args or {}), id=getattr(fc, "id", None)))
            elif getattr(part, "text", None) and not getattr(part, "thought", False):
                texts.append(part.text)
        out.text = "".join(texts).strip()
        return out

    def add_tool_results(self, results: list[tuple[ToolCall, dict[str, Any]]]) -> None:
        t = self.types
        parts = [
            t.Part(function_response=t.FunctionResponse(name=call.name, id=call.id, response=result))
            for call, result in results
        ]
        self.contents.append(t.Content(role="user", parts=parts))

    def add_user_text(self, text: str) -> None:
        t = self.types
        if self.contents and self.contents[-1].role == "user":
            self.contents[-1].parts.append(t.Part(text=text))
        else:
            self.contents.append(t.Content(role="user", parts=[t.Part(text=text)]))
