from __future__ import annotations

from ..config import Settings
from .base import Conversation, LLMProvider, LLMResponse, ProviderError, ToolCall, ToolSpec


def create_provider(settings: Settings) -> LLMProvider:
    """Build the provider chosen by LLM_PROVIDER (gemini | claude)."""
    name = settings.llm_provider.lower()
    if name == "gemini":
        from .gemini import GeminiProvider

        return GeminiProvider(settings.gemini_api_key, settings.model_name)
    if name in ("claude", "anthropic"):
        from .claude import ClaudeProvider

        return ClaudeProvider(
            settings.anthropic_api_key, settings.model_name, max_tokens=settings.max_output_tokens
        )
    raise ProviderError(f"Unknown LLM_PROVIDER {settings.llm_provider!r}. Use 'gemini' or 'claude'.")


__all__ = ["Conversation", "LLMProvider", "LLMResponse", "ProviderError", "ToolCall", "ToolSpec", "create_provider"]
