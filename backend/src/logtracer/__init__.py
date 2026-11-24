"""Log Tracer backend."""

__version__ = "0.1.0"


def main() -> None:
    """Start the API server: `uv run logtracer`."""
    import uvicorn

    uvicorn.run("logtracer.main:app", host="127.0.0.1", port=8000, reload=True)
