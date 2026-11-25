"""Provider-neutral LLM interface. Swap Gemini / Claude / Ollama without touching the agent."""
from __future__ import annotations

import logging
import time
from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

log = logging.getLogger(__name__)


class ProviderError(RuntimeError):
    """A readable error that is safe to show to the user (never contains API keys)."""


@dataclass
class ToolSpec:
    name: str
    description: str
    parameters: dict[str, Any]  # JSON schema, lowercase types, no $ref


@dataclass
class ToolCall:
    name: str
    args: dict[str, Any]
    id: str | None = None


@dataclass
class LLMResponse:
    text: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    input_tokens: int = 0
    output_tokens: int = 0


class Conversation(ABC):
    """One question's message history, in the provider's native format."""

    @abstractmethod
    def generate(self, force_tool: str | None = None) -> LLMResponse:
        """Call the model. ``force_tool`` makes it call that tool (used to force ``submit_answer``)."""

    @abstractmethod
    def add_tool_results(self, results: list[tuple[ToolCall, dict[str, Any]]]) -> None: ...

    @abstractmethod
    def add_user_text(self, text: str) -> None: ...


class LLMProvider(ABC):
    name: str
    model: str

    @abstractmethod
    def start(self, system: str, tools: list[ToolSpec], user_message: str) -> Conversation: ...


def with_retries[T](
    fn: Callable[[], T],
    is_retryable: Callable[[Exception], bool],
    *,
    attempts: int = 4,
    base_delay: float = 2.0,
    sleep: Callable[[float], None] = time.sleep,
    delay_for: Callable[[Exception], float | None] | None = None,
) -> T:
    """Retry rate limits / overload with exponential backoff (free tiers hit 429 often).

    ``delay_for`` can return the wait the provider asked for (e.g. a ``retry-after`` header);
    the longer of that and the backoff is used.
    """
    for attempt in range(1, attempts + 1):
        try:
            return fn()
        except Exception as exc:
            if attempt == attempts or not is_retryable(exc):
                raise
            delay = base_delay * 2 ** (attempt - 1)
            hint = delay_for(exc) if delay_for else None
            if hint is not None:
                delay = max(delay, hint)
            code = getattr(exc, "code", None) or getattr(exc, "status_code", None)
            log.warning(
                "LLM call failed (%s%s), retrying in %.0fs",
                type(exc).__name__, f" {code}" if code else "", delay,
            )
            sleep(delay)
    raise AssertionError("unreachable")
