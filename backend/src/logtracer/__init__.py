"""Log Tracer backend."""

__version__ = "0.1.0"


def main() -> None:
    """Start the API server with the settings from backend/.env: `uv run logtracer`."""
    import uvicorn

    from logtracer.core.config import get_settings

    settings = get_settings()
    uvicorn.run(
        "logtracer.main:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=settings.api_reload,
        log_level=settings.log_level,
    )
