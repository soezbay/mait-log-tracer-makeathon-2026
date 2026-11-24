"""Token and cost bookkeeping. Every LLM call is written to ``llm_calls`` (best effort).

Providers list prices in USD; ``llm_calls.cost_eur`` stores EUR, converted with ``EUR_PER_USD``.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .config import Settings
from .data_access import LogStore

# USD per 1M tokens (input, output). VERIFY on the provider's pricing page before quoting numbers in the
# pitch, or override with PRICE_INPUT_PER_MTOK / PRICE_OUTPUT_PER_MTOK in .env.
PRICES: dict[str, tuple[float, float]] = {
    "gemini-2.5-flash": (0.30, 2.50),
    "gemini-2.5-pro": (1.25, 10.00),
    "claude-sonnet-4-5": (3.00, 15.00),
}


def estimate_cost_eur(model: str, input_tokens: int, output_tokens: int, settings: Settings | None = None) -> float | None:
    """Estimated cost in EUR at list price (also for free-tier calls). None if the price is unknown."""
    if settings and settings.price_input_per_mtok is not None and settings.price_output_per_mtok is not None:
        p_in, p_out = settings.price_input_per_mtok, settings.price_output_per_mtok
    elif model in PRICES:
        p_in, p_out = PRICES[model]
    else:
        return None
    usd = (input_tokens * p_in + output_tokens * p_out) / 1_000_000
    rate = settings.eur_per_usd if settings else 0.86
    return round(usd * rate, 8)


@dataclass
class UsageTotals:
    provider: str
    model: str
    calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    duration_ms: int = 0
    cost_eur: float | None = 0.0
    per_call: list[dict] = field(default_factory=list)

    def add(self, conversation_id: str, input_tokens: int, output_tokens: int, duration_ms: int,
            settings: Settings | None, store: LogStore | None) -> None:
        cost = estimate_cost_eur(self.model, input_tokens, output_tokens, settings)
        self.calls += 1
        self.input_tokens += input_tokens
        self.output_tokens += output_tokens
        self.duration_ms += duration_ms
        self.cost_eur = None if (cost is None or self.cost_eur is None) else round(self.cost_eur + cost, 8)
        row = {
            "conversation_id": conversation_id,
            "provider": self.provider,
            "model": self.model,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "duration_ms": duration_ms,
            "cost_eur": cost,
        }
        self.per_call.append(row)
        if store is not None:
            store.save_llm_call(row)

    def summary(self) -> dict:
        return {
            "provider": self.provider,
            "model": self.model,
            "llm_calls": self.calls,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "llm_duration_ms": self.duration_ms,
            "cost_eur": self.cost_eur,
        }
