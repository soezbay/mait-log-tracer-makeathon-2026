# AGENTS.md: how to develop and document Log Tracer

Instructions for AI coding agents and humans working in this repository. Written in English; all code, comments, commits and docs are English too.

## 1. Start here

1. Read [docs/AI_LOG.md](docs/AI_LOG.md): one line per change, newest at the bottom. It tells you the current state and what is open.
2. Read your role in [docs/plan.en.md](docs/plan.en.md) §11 and the components in [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).
3. Check the frozen interfaces before you change anything that others use (§5 below).
4. Pull `main` before you start; commit and push to `main` or merge your short-lived branch into it (§8).

## 2. Project in one paragraph

Log Tracer is our solution for the MAIT Makeathon 2026 challenge "automated log file management with an AI assistant". It ingests the logs of 14 servers (Teamcenter, NX/JT converters, dispatcher, FMS, …) in 6 formats into DuckDB without modifying the originals, groups errors, detects anomalies, correlates them across systems, and lets an LLM explain root causes as hypotheses with evidence (file + line), uncertainty and verification steps. Backend: Python 3.12 + FastAPI. Frontend: React 19 + TypeScript (Vite). They talk only through the HTTP API.

## 3. Repository layout

```
AGENTS.md                  this file
dev.cmd, scripts/dev.ps1   start backend + frontend with one command (`.\dev`)
CLAUDE.md                  imports this file for Claude Code
docs/
  AI_LOG.md                one-line change log for agents (append after every change)
  WORKLOG.md               detailed change log for humans (append after every change)
  plan.en.md / plan.md     plan (English is the reference version)
  ARCHITECTURE.md          architecture (English is the reference version), ARCHITEKTUR.md (German)
  todo/                    personal TODO lists, git-ignored
contracts/examples/        example JSON per API endpoint (frozen interface)
backend/                   Python 3.12, uv, FastAPI
  src/logtracer/
    api/ services/ ingest/ normalize/ storage/ analysis/ assistant/ core/
  tests/
frontend/                  React 19 + TypeScript (Vite)   [planned]
eval/                      test questions + ground truth   [planned]
MAIT_Makeathon_Logpaket.zip  the log package, versioned with Git LFS (never edit)
MAIT_Makeathon_Logpaket/   extracted log data, READ ONLY, git-ignored (created from the ZIP)
data/                      derived DuckDB files and the extraction marker, git-ignored
```

## 4. Roles and ownership

| Role | Person | Owns |
|---|---|---|
| P1 ingest & storage | Safak | `ingest/`, `normalize/` (except `clock.py`), `storage/`, `api/health.py`, `api/ingest.py`, `api/events.py`, `api/sources.py`, `api/schemas.py`, `api/deps.py`, `services/event_service.py`, `services/ingest_service.py`, `scripts/ingest.py`, `scripts/make_fixture.py` |
| P2 analysis & correlation | Harsh | `analysis/`, `normalize/clock.py`, `api/analysis.py` |
| P3 AI assistant | Tarun | `assistant/`, `api/chat.py` |
| P4 frontend | Adnan | `frontend/` |
| P5 data, evaluation & pitch | open | `eval/`, `scripts/evaluate.py`, `api/eval.py`, `docs/`, `README.md` |

- Change only files your role owns. For shared files (`backend/src/logtracer/main.py`, `pyproject.toml`, `uv.lock`, `package.json`) keep changes minimal and tell the team.
- If a task needs a change in someone else's area, describe it in the open column of `docs/AI_LOG.md` instead of doing it.

## 5. Frozen interfaces

| Interface | File | Owner |
|---|---|---|
| DB schema | `backend/src/logtracer/storage/schema.sql` | P1 (analysis tables P2, assistant tables P3) |
| API contract | `docs/ARCHITECTURE.md` §5 + `contracts/examples/*.json` | owner of each endpoint |
| Assistant answer format | `backend/src/logtracer/assistant/answer.py` | P3 |

Changing an interface: agree with the affected roles first, then change schema/code **and** the example in `contracts/examples/` **and** `docs/ARCHITECTURE.md` in the same commit, and note it in both logs.

## 6. Development setup

Log package (Git LFS):
```powershell
git lfs install                     # once per machine (Git for Windows ships Git LFS)
git clone <repo>                    # LFS pulls MAIT_Makeathon_Logpaket.zip (~83 MB)
```
On every program start (API server, `scripts/ingest.py`, `scripts/make_fixture.py`) the backend checks the package: if the ZIP is missing or only an LFS pointer it runs `git lfs pull` for it (`AUTO_DOWNLOAD`), and if `MAIT_Makeathon_Logpaket/` is missing or incomplete it extracts the missing files once (`AUTO_EXTRACT`, first time ~1 min). Later starts take no time (marker in `data/logpaket.extracted.json`).

Backend:
```powershell
python -m pip install --user uv
cd backend; python -m uv sync
copy .env.example .env
python -m uv run logtracer          # API on http://localhost:8000, docs at /docs
python -m uv run pytest
python -m uv run ruff check .
```
Frontend: Node.js 22 or 24 LTS, `npm install --no-package-lock` (the team lockfile is `pnpm-lock.yaml`), `npm run dev` (port 5173, proxies `/api` to `:8000`).

Whole app with one command (repo root, Windows, cmd or PowerShell):
```powershell
.\dev                 # backend :8000 + frontend :5173, opens the browser; Ctrl+C stops both
.\dev -NoBrowser      # same without opening the browser
.\dev -Install        # also re-run npm install
```
`dev.cmd` calls `scripts/dev.ps1` (execution policy bypassed). It creates `backend/.env` from the example if missing, installs frontend packages on the first run, starts the backend, waits for `/api/health`, then starts Vite.

Configuration comes from `backend/.env` (see `backend/.env.example`). Relative paths resolve against `backend/`.

## 7. Engineering rules

**Data**
- Never modify, move or delete anything in `MAIT_Makeathon_Logpaket/`. Everything derived goes into DuckDB under `data/` and must be rebuildable by script.
- Every event keeps its origin: `source_id`, `line_start`, `line_end`, `raw`. No feature may lose that link.
- All timestamps are UTC. Keep the original in `ts_raw`; set `tz_assumed` when the source had no time zone.
- Levels are normalized to `DEBUG | INFO | WARN | ERROR | FATAL`.
- An unparseable line is stored with `parse_error`, never dropped and never aborts the ingest.

**DuckDB**
- One process writes the database file: API, ingest and watcher run in the same backend process. Scripts that write must not run while the backend is running.
- No primary key on `events` (bulk insert speed, updates of `template_id`). Uniqueness of `events.id` is the pipeline's job.
- Insert in batches (PyArrow), never row by row in loops.
- SQL lives in `storage/` (repositories); API routers and services do not contain raw SQL.

**Python**
- Python 3.12, type hints, Pydantic models for API and parser output, ruff (line length 100).
- Parsers return the shared `RawEvent` model; a new format means a new parser, not changes elsewhere.
- Keep functions small and testable; no hidden global state except the settings and the single DB connection.

**API**
- All routes under `/api`. Times ISO-8601 UTC with `Z`. Lists are paginated: `{"items", "total", "limit", "offset"}`.
- Streaming uses SSE via FastAPI's built-in `fastapi.sse`. `GET` streams can be read with `EventSource`; the `POST /api/chat` stream must be read with `fetch` (EventSource is GET-only).

**LLM / assistant**
- The LLM never receives whole log files. It gets context only through tools that run SQL with a `LIMIT`.
- Every cause the assistant names must cite existing event IDs; the backend validates them.
- Every LLM call is recorded in `llm_calls` (tokens, duration, cost). The API key lives only in `backend/.env`.
- Harmless ERRORs (e.g. "Transient retry recovered") must not be named as a root cause; same job number does not always mean the same job.

**Tests**
- Parser tests use real sample lines from the log package (multi-line CSV, cp1252 file, `.gz`, time-only free text, unparseable line).
- Before every commit: `pytest` passes and `ruff check` is clean.

## 8. Git workflow

**`main` is the only shared branch.** There is no `develop` branch any more (removed on 2026-11-24 to avoid merge conflicts between two long-lived branches).

| Branch | Purpose | Who writes to it |
|---|---|---|
| `main` | shared state of the project, demo and pitch | everyone |
| `p<N>/<topic>` | optional short-lived branch for bigger changes, e.g. `p2/drain3-templates` | only the owner of the role |

Flow:
1. Before you start: `git switch main`, `git pull`.
2. Small change in your own folders: commit on `main`. Bigger change: `git switch -c p<N>/<topic>`, and merge it back into `main` the same day (pull request with base `main`, or local merge).
3. Before every push: `pytest` + `ruff check` pass, then `git pull --rebase` (rebases only your unpushed commits) and `git push`.
4. Never rewrite pushed history on `main` (no force push, no reset of pushed commits).

Rules:
- Small, focused commits. Message: imperative English subject (≤ 72 chars), body with bullets for what and why.
- Pull often (at least before every push) so conflicts stay small; touch only files your role owns.
- Never commit: `.env`, API keys, `*.duckdb`, `MAIT_Makeathon_Logpaket/`, `docs/todo/`.

## 9. Documentation and work logging (mandatory)

After **every** task or change, before you finish, update both logs in English and commit them together with the change.

**1. `docs/AI_LOG.md`**: exactly one line, appended inside the code block at the bottom:
```
date time | role | area | change | files | commit | open
```
- `date time`: `YYYY-MM-DD HH:MM` (local time)
- `role`: `P1`–`P5` or `all`
- `area`: short tag, e.g. `ingest`, `storage`, `api`, `analysis`, `assistant`, `frontend`, `eval`, `docs`, `git`, `decision`
- `change`: what changed and the key facts, one line, no line breaks
- `files`: main paths, comma-separated
- `commit`: short hash, or `self` if the line is part of that commit, or `-`
- `open`: what is left or blocked, or `-`

Example:
```
2026-11-24 11:30 | P1 | storage | schema.sql: servers, sources, events (no PK on events) + proposed P2/P3 tables; 6 tests pass | backend/src/logtracer/storage/ | 9d90778 | freeze with P2+P3 at 13:00
```

**2. `docs/WORKLOG.md`**: a short entry under the day's heading:
```
### <title>
- **What:** …
- **Why:** …
- **Where:** files, commit
- **Checks:** tests, manual checks (if any)
- **Open:** … (if any)
```

**3. Other docs**: if the change affects architecture, interfaces or the plan, update `docs/ARCHITECTURE.md`, `contracts/examples/` and `docs/plan.en.md` in the same commit. English documents are the reference; German versions may lag behind.

Decisions that change no file (e.g. "no Docker") are logged too, with `area` = `decision`.

## 10. Definition of done for a task

- [ ] Code in the owner's folders, tests added or updated
- [ ] `pytest` passes, `ruff check` clean
- [ ] Interfaces unchanged, or changed with agreement + updated examples + docs
- [ ] One line in `docs/AI_LOG.md`, entry in `docs/WORKLOG.md`
- [ ] Committed with an English message and pushed to `main` (directly or via your short-lived branch)

## 11. Data quick reference

- 14 servers (7 Linux, 7 Windows), path layout `<server>/logs/<application>/<component…>/<file>`; components can have 2 levels (`translators/nx_jt`).
- 13,643 log files, 5,068 unique (`_runNN` files are byte-identical copies), ~1.67 M events, ~3,345 ERRORs.
- Formats: `.log` key=value · `.txt` with JSON payload · `.csv` with `;` and quoted multi-line stack traces · `.jsonl` / `.jsonl.gz` · `.xml` (one `<Event>` per line) · `import_*.log` free text (some lines have only a time).
- One Windows-1252 file: `mait_win04_plm_sync/logs/cad/cad_export/creative_2026-11-24.txt`.
- Data sets: October `ki-integriert` (with `trace_id`, incidents `INC-01…10`), 6 Oct `import_*`, 23 Nov mostly normal (baseline, but contains failing `JOB-1xxx`), 24 Nov `creative_*` scenarios.
- Known scenarios: `JOB-2003` (converter SUCCESS, FMS upload rejected, publish fails), `JOB-2010` (missing reference `DEMO-Seal-17/C`), `JOB-2001` (clock behind, `clock_offset_seconds: -94`).
- Missing docs referenced by the package README: `_dokumentation/FORMATE.md`, `INTEGRATION.md` (ask the mentor).
