"""Settings from environment variables and `backend/.env` (template: `backend/.env.example`)."""

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

    # --- Paths (relative paths are resolved against backend/) ---------------------------
    log_root: Path = Path("../MAIT_Makeathon_Logpaket")
    logpaket_zip: Path = Path("../MAIT_Makeathon_Logpaket.zip")  # Git LFS, extracted on start
    auto_extract: bool = True
    auto_download: bool = True  # `git lfs pull` the ZIP on start if it is missing
    db_path: Path = Path("../data/logtracer.duckdb")
    fixture_db_path: Path = Path("../data/fixture.duckdb")
    eval_questions_path: Path = Path("../eval/questions.yaml")

    # --- API server ------------------------------------------------------------------------
    api_host: str = "127.0.0.1"
    api_port: int = 8000
    api_reload: bool = True
    cors_origins: list[str] = ["http://localhost:5173"]
    log_level: str = "info"

    # --- Ingest (P1) -----------------------------------------------------------------------
    ingest_batch_size: int = 50_000
    ingest_workers: int = 1  # >1: parse files in parallel processes, one writer stays
    default_timezone: str = "UTC"  # for timestamps without a time zone (import_*.log)

    # --- Continuous ingest (P1, day 3) -----------------------------------------------------
    watch_enabled: bool = False
    watch_debounce_s: float = 1.5
    watch_rescan_s: float = 10.0  # safety net: full size/mtime check every N s (0 = off)

    # --- LLM (P3) --------------------------------------------------------------------------
    llm_provider: str = "claude"  # claude | gemini | ollama
    llm_model: str = "claude-sonnet-5-5"
    anthropic_api_key: SecretStr | None = None
    gemini_api_key: SecretStr | None = None
    llm_max_tool_rounds: int = 8
    llm_max_output_tokens: int = 4096
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "llama3.1"

    @field_validator("log_root", "logpaket_zip", "db_path", "fixture_db_path",
                     "eval_questions_path")
    @classmethod
    def resolve_relative_to_backend(cls, value: Path) -> Path:
        """Relative paths are resolved against `backend/`, not the current directory."""
        return value if value.is_absolute() else (BACKEND_DIR / value).resolve()


@lru_cache
def get_settings() -> Settings:
    return Settings()
