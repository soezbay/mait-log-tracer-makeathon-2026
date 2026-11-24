from pathlib import Path

from logtracer.core.config import BACKEND_DIR, Settings


def test_example_env_matches_settings():
    """Every key in .env.example is a real setting, and every setting is documented there."""
    example = (BACKEND_DIR / ".env.example").read_text(encoding="utf-8")
    keys = {
        line.split("=", 1)[0].strip().lower()
        for line in example.splitlines()
        if line.strip() and not line.lstrip().startswith("#") and "=" in line
    }
    assert keys == set(Settings.model_fields)


def test_example_env_loads(monkeypatch):
    for key in Settings.model_fields:
        monkeypatch.delenv(key.upper(), raising=False)
    settings = Settings(_env_file=BACKEND_DIR / ".env.example")
    assert settings.cors_origins == ["http://localhost:5173"]
    assert settings.api_port == 8000
    assert settings.anthropic_api_key is None or settings.anthropic_api_key.get_secret_value() == ""
    assert settings.log_root.is_absolute()
    assert settings.db_path == (BACKEND_DIR / "../data/logtracer.duckdb").resolve()


def test_absolute_paths_are_kept(tmp_path):
    settings = Settings(_env_file=None, db_path=tmp_path / "x.duckdb")
    assert settings.db_path == Path(tmp_path / "x.duckdb")
