# Log Tracer backend

Python 3.12 + FastAPI. See [docs/ARCHITECTURE.md](../docs/ARCHITECTURE.md) for components and ownership.

## Setup

```powershell
python -m pip install --user uv
uv sync
copy .env.example .env
```

## Run

```powershell
uv run logtracer
```

API: http://localhost:8000/api/health · Docs: http://localhost:8000/docs

## Test and lint

```powershell
uv run pytest
uv run ruff check .
```
