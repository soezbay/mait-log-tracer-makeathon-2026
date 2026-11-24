"""Settings from environment variables and `backend/.env`."""

from functools import lru_cache
from pathlib import Path

from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# src/logtracer/core/config.py -> backend/
BACKEND_DIR = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BACKEND_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Data
    log_root: Path = Path("../MAIT_Makeathon_Logpaket")
    db_path: Path = Path("../data/logtracer.duckdb")

    # LLM (used by the assistant, P3)
    llm_provider: str = "claude"
    llm_model: str = "claude-sonnet-5-5"
    anthropic_api_key: SecretStr | None = None

    # Continuous ingest (P1, day 3)
    watch_enabled: bool = False

    # Frontend dev server
    cors_origins: list[str] = ["http://localhost:5173"]

    @field_validator("log_root", "db_path")
    @classmethod
    def resolve_relative_to_backend(cls, value: Path) -> Path:
        """Relative paths are resolved against `backend/`, not the current directory."""
        return value if value.is_absolute() else (BACKEND_DIR / value).resolve()


@lru_cache
def get_settings() -> Settings:
    return Settings()
