"""Claude provider (anthropic SDK). Use it for the evaluation run and the pitch demo."""
from __future__ import annotations

import json
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


class ClaudeProvider(LLMProvider):
    name = "claude"

    def __init__(self, api_key: str | None, model: str, client: Any | None = None,
                 max_tokens: int = 4096, sleep: Callable[[float], None] | None = None):
        import anthropic

        if client is None:
            if not api_key:
                raise ProviderError("ANTHROPIC_API_KEY is not set (put it in backend/.env).")
            client = anthropic.Anthropic(api_key=api_key)
        self.client = client
        self.model = model
        self.max_tokens = max_tokens
        self._sleep = sleep

    def start(self, system: str, tools: list[ToolSpec], user_message: str) -> Conversation:
        return ClaudeConversation(self, system, tools, user_message)


class ClaudeConversation(Conversation):
    def __init__(self, provider: ClaudeProvider, system: str, tools: list[ToolSpec], user_message: str):
        self.p = provider
        self.system = system
        self.tools = [{"name": t.name, "description": t.description, "input_schema": t.parameters} for t in tools]
        self.messages: list[dict[str, Any]] = [{"role": "user", "content": user_message}]

    @staticmethod
    def _retryable(exc: Exception) -> bool:
        return getattr(exc, "status_code", None) in (429, 500, 502, 503, 504, 529)

    def generate(self, force_tool: str | None = None) -> LLMResponse:
        kwargs: dict[str, Any] = {
            "model": self.p.model,
            "max_tokens": self.p.max_tokens,
            "system": self.system,
            "tools": self.tools,
            "messages": self.messages,
        }
        if force_tool:
            kwargs["tool_choice"] = {"type": "tool", "name": force_tool}
        retry_kwargs = {"sleep": self.p._sleep} if self.p._sleep else {}
        try:
            resp = with_retries(lambda: self.p.client.messages.create(**kwargs), self._retryable, **retry_kwargs)
        except Exception as exc:
            status = getattr(exc, "status_code", None)
            if status == 429:
                raise ProviderError("Claude rate limit reached. Wait a moment and try again.") from exc
            if status in (400, 401, 403, 404):
                raise ProviderError(f"Claude rejected the request ({status}). Check ANTHROPIC_API_KEY and LLM_MODEL.") from exc
            raise ProviderError(f"Claude call failed: {type(exc).__name__}") from exc

        usage = getattr(resp, "usage", None)
        out = LLMResponse(
            input_tokens=getattr(usage, "input_tokens", 0) or 0,
            output_tokens=getattr(usage, "output_tokens", 0) or 0,
        )
        texts = []
        for block in resp.content:
            if block.type == "text":
                texts.append(block.text)
            elif block.type == "tool_use":
                out.tool_calls.append(ToolCall(name=block.name, args=dict(block.input or {}), id=block.id))
        out.text = "".join(texts).strip()
        self.messages.append({"role": "assistant", "content": resp.content})
        return out

    def add_tool_results(self, results: list[tuple[ToolCall, dict[str, Any]]]) -> None:
        blocks = [
            {"type": "tool_result", "tool_use_id": call.id, "content": json.dumps(result, ensure_ascii=False, default=str)}
            for call, result in results
        ]
        self.messages.append({"role": "user", "content": blocks})

    def add_user_text(self, text: str) -> None:
        last = self.messages[-1]
        if last["role"] == "user" and isinstance(last["content"], list):
            last["content"].append({"type": "text", "text": text})
        elif last["role"] == "user":
            last["content"] = [{"type": "text", "text": last["content"]}, {"type": "text", "text": text}]
        else:
            self.messages.append({"role": "user", "content": text})
