# Log Tracer backend

Python 3.12 + FastAPI. See [docs/ARCHITECTURE.md](../docs/ARCHITECTURE.md) for components and ownership.

## Setup

The log package comes as `MAIT_Makeathon_Logpaket.zip` via Git LFS (`git lfs install` once per machine). The backend downloads (`git lfs pull`) and extracts it automatically on start if needed.

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
