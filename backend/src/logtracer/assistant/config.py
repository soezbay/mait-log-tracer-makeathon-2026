"""Settings for the assistant, read from environment variables and ``backend/.env``.

Same file and path rules as ``core/config.py`` (P1): ``.env`` is always ``backend/.env`` and relative
paths resolve against ``backend/``, no matter which folder the app is started from.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import AliasChoices, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from logtracer.core.config import BACKEND_DIR

DEFAULT_MODELS = {
    "gemini": "gemini-3.6-flash",
    "claude": "claude-sonnet-5-5",
}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BACKEND_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    llm_provider: str = "gemini"  # gemini | claude
    llm_model: str | None = None  # default depends on provider
    db_path: Path = Path("../data/logtracer.duckdb")

    gemini_api_key: str | None = Field(
        default=None, validation_alias=AliasChoices("GEMINI_API_KEY", "GOOGLE_API_KEY")
    )
    anthropic_api_key: str | None = Field(default=None, validation_alias=AliasChoices("ANTHROPIC_API_KEY"))

    # Optional price override (USD per 1M tokens, as the providers list them). Use it for the pitch.
    price_input_per_mtok: float | None = None
    price_output_per_mtok: float | None = None
    # llm_calls stores cost in EUR (schema.sql). Verify the current rate before quoting numbers.
    eur_per_usd: float = 0.86

    # LLM_MAX_TOOL_ROUNDS / LLM_MAX_OUTPUT_TOKENS are the names documented in .env.example (P1).
    max_rounds: int = Field(default=8, validation_alias=AliasChoices("LLM_MAX_TOOL_ROUNDS", "MAX_ROUNDS"))
    max_tool_calls: int = 14
    max_output_tokens: int = Field(
        default=4096, validation_alias=AliasChoices("LLM_MAX_OUTPUT_TOKENS", "MAX_OUTPUT_TOKENS")
    )

    @field_validator("db_path")
    @classmethod
    def _resolve_relative_to_backend(cls, value: Path) -> Path:
        return value if value.is_absolute() else (BACKEND_DIR / value).resolve()

    @property
    def model_name(self) -> str:
        return self.llm_model or DEFAULT_MODELS.get(self.llm_provider, "")


@lru_cache
def get_settings() -> Settings:
    return Settings()
