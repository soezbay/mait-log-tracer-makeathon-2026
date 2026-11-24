"""Groq provider (groq SDK, OpenAI-compatible chat completions with tool calling).

Groq serves open models (e.g. ``openai/gpt-oss-120b``, ``qwen/qwen3.8-27b``) with very low latency.
Free and developer plans have tokens-per-minute limits, so 429 answers are retried after the wait
Groq asks for in its ``retry-after`` header.
"""
from __future__ import annotations

import json
import logging
import re
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

# Reasoning models can put their thinking into the text as <think>...</think>; it is not answer text.
_THINK = re.compile(r"<think>.*?</think>", re.DOTALL)
_MAX_WAIT_S = 60.0


def _describe(exc: Exception) -> str:
    """HTTP status and Groq's error message (never contains the API key)."""
    status = getattr(exc, "status_code", None)
    body = getattr(exc, "body", None)
    message = None
    if isinstance(body, dict):
        err = body.get("error", body)
        if isinstance(err, dict):
            message = err.get("message")
    message = message or str(exc)
    head = str(status) if status else type(exc).__name__
    return f"{head}: {' '.join(str(message).split())[:300]}"


def _error_code(exc: Exception) -> str | None:
    body = getattr(exc, "body", None)
    if isinstance(body, dict):
        err = body.get("error", body)
        if isinstance(err, dict):
            return err.get("code")
    return None


def _retry_after(exc: Exception) -> float | None:
    """Seconds Groq asks us to wait (``retry-after`` header), capped at one minute."""
    response = getattr(exc, "response", None)
    headers = getattr(response, "headers", None) or {}
    try:
        value = float(headers.get("retry-after"))
    except (TypeError, ValueError):
        return None
    return min(max(value, 0.5), _MAX_WAIT_S)


class GroqProvider(LLMProvider):
    name = "groq"

    def __init__(self, api_key: str | None, model: str, client: Any | None = None,
                 max_tokens: int = 4096, reasoning_effort: str | None = None,
                 sleep: Callable[[float], None] | None = None):
        if client is None:
            if not api_key:
                raise ProviderError("GROQ_API_KEY is not set (put it in backend/.env).")
            from groq import Groq  # imported lazily so the package is optional

            # max_retries=0: with_retries is the only retry layer (it honours retry-after).
            client = Groq(api_key=api_key, max_retries=0)
        self.client = client
        self.model = model
        self.max_tokens = max_tokens
        self.reasoning_effort = reasoning_effort
        self._sleep = sleep

    def start(self, system: str, tools: list[ToolSpec], user_message: str) -> Conversation:
        return GroqConversation(self, system, tools, user_message)


class GroqConversation(Conversation):
    def __init__(self, provider: GroqProvider, system: str, tools: list[ToolSpec], user_message: str):
        self.p = provider
        self.tools = [
            {"type": "function",
             "function": {"name": t.name, "description": t.description, "parameters": t.parameters}}
            for t in tools
        ]
        self.messages: list[dict[str, Any]] = [
            {"role": "system", "content": system},
            {"role": "user", "content": user_message},
        ]

    @staticmethod
    def _retryable(exc: Exception) -> bool:
        if getattr(exc, "status_code", None) in (429, 500, 502, 503, 504):
            return True
        return type(exc).__name__ in ("APIConnectionError", "APITimeoutError")

    def generate(self, force_tool: str | None = None) -> LLMResponse:
        kwargs: dict[str, Any] = {
            "model": self.p.model,
            "messages": self.messages,
            "tools": self.tools,
            "tool_choice": (
                {"type": "function", "function": {"name": force_tool}} if force_tool else "auto"
            ),
            "max_completion_tokens": self.p.max_tokens,
        }
        if self.p.reasoning_effort:
            kwargs["reasoning_effort"] = self.p.reasoning_effort
        retry_kwargs: dict[str, Any] = {"delay_for": _retry_after}
        if self.p._sleep:
            retry_kwargs["sleep"] = self.p._sleep
        try:
            resp = with_retries(
                lambda: self.p.client.chat.completions.create(**kwargs), self._retryable, **retry_kwargs
            )
        except Exception as exc:
            status = getattr(exc, "status_code", None)
            detail = _describe(exc)
            if status == 400 and _error_code(exc) == "tool_use_failed":
                # The model wrote a malformed tool call. Keep the history valid; the agent nudges it.
                log.warning("Groq tool_use_failed, asking the model again [%s]", detail)
                return LLMResponse()
            if status == 429:
                raise ProviderError(
                    f"Groq rate limit reached (tokens or requests per minute). Wait a minute or "
                    f"choose another LLM_MODEL (now {self.p.model!r}). [{detail}]"
                ) from exc
            if status == 413:
                raise ProviderError(
                    f"Groq: the request is larger than this model's per-minute token limit allows. "
                    f"Choose a model with a higher limit (now {self.p.model!r}). [{detail}]"
                ) from exc
            if status in (400, 401, 403, 404):
                raise ProviderError(
                    f"Groq rejected the request. Check GROQ_API_KEY and LLM_MODEL "
                    f"(now {self.p.model!r}). [{detail}]"
                ) from exc
            if status in (500, 502, 503, 504):
                raise ProviderError(
                    f"Groq server error, usually temporary. Try again in a few minutes. [{detail}]"
                ) from exc
            raise ProviderError(f"Groq call failed. [{detail}]") from exc

        usage = getattr(resp, "usage", None)
        out = LLMResponse(
            input_tokens=getattr(usage, "prompt_tokens", 0) or 0,
            output_tokens=getattr(usage, "completion_tokens", 0) or 0,
        )
        choices = getattr(resp, "choices", None) or []
        msg = choices[0].message if choices else None
        if msg is None:
            log.warning("Groq returned no choices")
            return out
        out.text = _THINK.sub("", msg.content or "").strip()
        raw_calls = []
        for i, tc in enumerate(getattr(msg, "tool_calls", None) or []):
            fn = tc.function
            try:
                args = json.loads(fn.arguments or "{}")
            except json.JSONDecodeError:
                log.warning("Groq tool call %s had invalid JSON arguments", fn.name)
                args = {}
            if not isinstance(args, dict):
                args = {}
            call_id = tc.id or f"call_{len(self.messages)}_{i}"
            out.tool_calls.append(ToolCall(name=fn.name, args=args, id=call_id))
            raw_calls.append({"id": call_id, "type": "function",
                              "function": {"name": fn.name, "arguments": fn.arguments or "{}"}})
        assistant: dict[str, Any] = {"role": "assistant", "content": out.text or None}
        if raw_calls:
            assistant["tool_calls"] = raw_calls
        if assistant["content"] is not None or raw_calls:
            self.messages.append(assistant)
        return out

    def add_tool_results(self, results: list[tuple[ToolCall, dict[str, Any]]]) -> None:
        for call, result in results:
            self.messages.append({
                "role": "tool",
                "tool_call_id": call.id,
                "content": json.dumps(result, ensure_ascii=False, default=str),
            })

    def add_user_text(self, text: str) -> None:
        last = self.messages[-1]
        if last["role"] == "user" and isinstance(last.get("content"), str):
            last["content"] += "\n\n" + text
        else:
            self.messages.append({"role": "user", "content": text})
