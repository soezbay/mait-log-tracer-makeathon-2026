# Work log

English log of what was done, written after every task or change. Newest entries at the bottom.
Format: date · what · why · where (files, commits) · open points.
For AI agents there is a compact one-line version: [AI_LOG.md](AI_LOG.md).

---

## 2026-11-23

### Repository and first plan
- **What:** Created the Git repo (`main`), `.gitignore`, a first 3+1-day plan in German (`plan.md`) and English (`plan.en.md`).
- **Why:** Common starting point for the MAIT challenge "automated log file management with an AI assistant".
- **Where:** commit `b068abb`.

### Log package analysis
- **What:** Scanned `MAIT_Makeathon_Logpaket/`: 14 servers (7 Linux, 7 Windows), 13,643 log files, only 5,068 with distinct content (`_runNN` copies), ~1.67 M events, 3,345 ERRORs, 6 formats (key=value `.log`, `.txt` with JSON, `;`-CSV with multi-line stack traces, JSONL/JSONL.gz, XML, free-text `import_*.log`), one Windows-1252 file. Plans rewritten around the real data; log package excluded from Git (862 MB).
- **Why:** Base the plan on facts instead of assumptions.
- **Where:** `plan.md`, `plan.en.md`, `.gitignore`.

### Architecture documentation
- **What:** Architecture doc with a strict frontend/backend split (React + TypeScript ↔ FastAPI via REST/SSE), frameworks, components, API contract, flows, data model, decisions. German version first, then English.
- **Why:** Shared technical picture so team members can work in parallel.
- **Where:** `docs/ARCHITEKTUR.md`, `docs/ARCHITECTURE.md`; commits `b068abb`, `e542564`.

### Rename and phased TODO
- **What:** Working title LogLens → Log Tracer; phased TODO list added to the plans.
- **Where:** commit `bdc03de`.

### Pitch deck
- **What:** Slide deck (claude.ai Slides artifact): title, problem, idea & tools, phase table (automatic analysis vs. AI on demand), frontend/backend architecture with the rendered component diagram.
- **Why:** Day-1 pitch material.
- **Where:** artifact "Log Tracer – Pitch" (not in Git); exported files in `docs/` were added by Safak (commit `9a81c9a`).

---

## 2026-11-24

### 5-person work split
- **What:** English plan §11/§16 rewritten for 5 roles with own folders, three frozen interfaces (DB schema, API contract with example JSONs, answer format), stand-in data, per-person schedule. Owners: P1 Safak, P2 Harsh, P3 Tarun, P4 Adnan, P5 open (fallback split).
- **Why:** Everyone can work independently without waiting on others.
- **Where:** `plan.en.md`; commit `4d6c467`.

### Review and corrections (data + web sources)
- **What:** Checked plans and architecture against the log package and current docs.
  - Demo scenario `JOB-2003`: real cause is a rejected FMS upload (missing write permission), not the missing `DEMO-Seal-17/C` reference; `JOB-2010` and `JOB-1003` are separate cases.
  - 23 Nov baseline contains failing `JOB-1xxx` jobs; clock-skew entry carries `clock_offset_seconds` and `observed_at`.
  - Tech: React 18 → 19, Node 20 (EOL) → 22/24 LTS, `sse-starlette` → FastAPI built-in SSE, `tzdata` for `zoneinfo` on Windows, `POST /chat` stream read via `fetch` (EventSource is GET-only), DuckDB concurrency wording, `incidents` table/endpoint, notes on unmaintained Drain3 and react-cytoscapejs.
- **Why:** Remove factual errors before the team builds on them.
- **Where:** both plans and both architecture docs; commit `4c18416`.

### P1 TODO plan (Safak)
- **What:** Personal TODO for P1 ingest & storage: deliverables with deadlines, setup commands, schema draft, parser notes from the real data, day 2–4 tasks.
- **Where:** `docs/todo/P1-safak.md` (local only, `docs/todo/` is git-ignored).

### Backend skeleton (P1, first task)
- **What:** uv project with Python 3.12, dependencies (FastAPI, Uvicorn, Pydantic, pydantic-settings, DuckDB, PyArrow, pandas, watchdog, tzdata; dev: pytest, ruff, httpx), settings from `backend/.env`, `GET /api/health`, CORS for the Vite dev server, package folders for all roles, tests, backend README.
- **Why:** Everyone can start in their own folder; the frontend can connect immediately.
- **Checks:** 2 tests passed, ruff clean, live server: `/api/health` and `/docs` return 200, CORS preflight 200.
- **Where:** `backend/`; commit `0f737e4` on `p1/backend-setup`, fast-forwarded into `main` and pushed.
- **Note:** uv's Python 3.12 download failed to create its version link on this machine; the venv was created directly from the downloaded interpreter.

### Work log
- **What:** Created this log; from now on an English entry is added after every task or change.
- **Where:** `docs/WORKLOG.md`; commit `39a03a2`, pushed on `p1/backend-setup` and fast-forwarded into `main`.

### Docker decision
- **What:** Decided not to use Docker for now.
- **Why:** uv + lockfile already give a reproducible environment; on Windows, bind-mounting the 862 MB log package slows the ingest and file-change events do not reach the container reliably (would break the live watcher demo).

### Interfaces 1 and 2 (P1, deadline 13:00)
- **What:**
  - `storage/schema.sql`: tables `servers`, `sources`, `events` (P1) plus proposed tables for P2 (`templates`, `error_groups`, `group_members`, `anomalies`, `correlations`, `incidents`) and P3 (`hypotheses`, `llm_calls`, `chat_messages`), to be confirmed with Harsh and Tarun.
  - New `servers` table, because `server_info.json` differs per server (some have `role`, others only `synthetic_demo_role`/`origin`).
  - No primary key on `events`: DuckDB checks constraints eagerly, which slows bulk inserts and can break the `UPDATE` of `template_id` by P2.
  - `storage/db.py`: `connect()` and idempotent `init_schema()`.
  - `contracts/examples/`: example responses for all P1 endpoints (`health`, `stats`, `sources`, `events`, `event`, `event_context`, `ingest_progress` SSE), built from the real `JOB-2003` chain, plus a README with the rules.
- **Why:** Harsh, Tarun and Adnan can build against fixed interfaces without waiting for the ingest.
- **Checks:** 6 tests passed (schema creates all tables, idempotent, insert/select with JSON `attrs`, `UPDATE` on events works), ruff clean, all example JSONs parse.
- **Where:** `backend/src/logtracer/storage/`, `backend/tests/test_schema.py`, `contracts/examples/`.
- **Open:** walk the team through schema and examples and freeze them; `starlette.testclient` warns that `httpx` should be replaced by `httpx2` (switch was not done, harmless for now).

### One-line AI log
- **What:** Added `docs/AI_LOG.md` with one line per change (`date time | role | area | change | files | commit | open`) and back-filled all work so far. This file stays the detailed human log.
- **Why:** AI agents can read the project state quickly and cheaply from one compact file.
- **Where:** `docs/AI_LOG.md`, `docs/WORKLOG.md`.

### AGENTS.md (development and documentation rules)
- **What:** `AGENTS.md` at the repo root: where to start, project summary, layout, roles and file ownership, frozen interfaces and how to change them, setup commands, engineering rules (data, DuckDB, Python, API, LLM, tests), git workflow, mandatory logging in `AI_LOG.md` and `WORKLOG.md` with formats, definition of done, data quick reference. `CLAUDE.md` imports it so Claude Code sessions of all team members follow the same rules.
- **Why:** Every person and every AI agent works and documents the same way.
- **Where:** `AGENTS.md`, `CLAUDE.md`.
- **Open:** `AGENTS.md` links to `docs/plan.en.md`; the move of the plans into `docs/` still has to be committed.

**Open (not done by Claude):** `plan.md`/`plan.en.md` were moved to `docs/` and `docs/todo/` was added to `.gitignore` locally; not committed yet. Links to `../plan*.md` in the architecture docs and the P1 TODO need updating after that move.
