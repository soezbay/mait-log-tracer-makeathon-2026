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

### Plans moved into docs/
- **What:** `plan.md` and `plan.en.md` now live in `docs/` (move by Safak, committed now). Fixed relative links in plans and architecture docs and the repo-structure blocks; `docs/todo/` is git-ignored. Checked tool support: Codex reads `AGENTS.md` natively, Claude Code reads `CLAUDE.md`, which imports `AGENTS.md`, so both follow the same rules.
- **Where:** `docs/plan*.md`, `docs/ARCHITECTURE.md`, `docs/ARCHITEKTUR.md`, `.gitignore`.

### Ingest steps 1-3: scan, read, file dedupe (P1)
- **What:**
  - `ingest/scanner.py`: finds all servers (`<server>/logs/…`, folders starting with `_` are skipped) and log files; reads `server_info.json`; derives application and component (components can have two levels, e.g. `translators/nx_jt`); skips `README.md` and `server_info.json`.
  - `ingest/reader.py`: decompresses `.gz` in memory, decodes UTF-8 (with/without BOM) with Windows-1252 fallback, splits lines on `
` only and strips `
`.
  - `ingest/fingerprint.py`: SHA-256 over the decompressed bytes and a duplicate index (first file per hash is the original).
  - `ingest/pipeline.py` + `storage/repositories/sources.py`: full scan writes `servers` and `sources` in one PyArrow batch; duplicates get `duplicate_of` and are not decoded.
  - `backend/scripts/ingest.py --scan-only` prints a JSON summary.
  - Schema: `sources.source_id` is now assigned by the pipeline (sequence default removed) so explicit IDs and defaults cannot collide.
- **Why:** Foundation for the parsers; confirms file counts, duplicates and encodings before parsing.
- **Checks:** 12 tests pass (layout, multi-level components, gz, cp1252, BOM, CRLF, duplicate detection incl. `.gz` vs plain, idempotent rescan), ruff clean. Real run: 14 servers, 13,643 files, 5,068 unique, 8,575 duplicates, 460 MB unique decompressed, 1 cp1252 original, 0 errors, 18.6 s. Matches the earlier analysis.
- **Where:** `backend/src/logtracer/ingest/`, `backend/src/logtracer/storage/`, `backend/scripts/ingest.py`, `backend/tests/test_scan.py`; branch `p1/ingest`.
- **Commit:** `4d0ea40`.

### Ingest steps 4-5: format detection and parsers (P1)
- **What:**
  - `ingest/models.py`: shared `RawEvent` (line range, raw text, timestamp text, level, host, component, IDs, message, `attrs`, `parse_error`) and `ParseContext` (fallback host/component, default date).
  - `ingest/detector.py`: format by extension for `.jsonl(.gz)`, `.csv`, `.xml`; `.log`/`.txt` by the first line, because `creative_*.log` files use the bracket-JSON shape, not key=value.
  - Parsers: `kv_log` (key=value pairs from the message into `attrs`), `bracket_json` (JSON payload incl. `trace_id`, `clock_offset_seconds`, `observed_at`), `csv_semicolon` (csv module, multi-line stack traces with correct line ranges), `jsonl`, `xml_events` (one `<Event>` per line), `freetext` (pipe, bracket with optional host, tagged `TC.*`, time-only lines). Unmatched lines are continuations; nothing is dropped.
  - Time-only lines get the most common date of the `import_*` files (2026-10-06) and `attrs.time_only`.
  - `ingest/parse_run.py` + `scripts/ingest.py --parse-dry-run`: parses all unique files, stores the format in `sources.format` (duplicates inherit it), prints statistics.
- **Checks:** 24 tests pass (9 parser tests with real line shapes), ruff clean. Dry run on the real package: 1,673,792 events from 5,068 files in 13.5 s, **0 parse errors**; only 1 multi-line event; 5 time-only lines.
- **Where:** `backend/src/logtracer/ingest/`, `backend/tests/test_parsers.py`.
- **Open:** normalization (UTC, level mapping, event dedupe) and writing `events` to DuckDB.

### Configuration: .env and .env.example
- **What:** `core/config.py` now holds every setting: paths (log package, DB, fixture DB, eval questions), API server (host, port, reload, CORS, log level), ingest (batch size, workers, default time zone), watcher (on/off, debounce), LLM (provider, model, API key, tool rounds, output limit, Ollama URL/model). `backend/.env.example` documents all of them with defaults; a local `backend/.env` was created from it (git-ignored, API key empty). `uv run logtracer` now uses host/port/reload/log level from the settings. A test checks that `.env.example` and the settings stay in sync.
- **Why:** One place for all configuration; nobody hard-codes paths or keys.
- **Where:** `backend/src/logtracer/core/config.py`, `backend/.env.example`, `backend/src/logtracer/__init__.py`, `backend/tests/test_config.py`.
- **Open:** frontend `.env` (`VITE_…`) once the frontend exists.

### GitHub push access
- **What:** Checked the repository via the public GitHub API: public repo, `main` is not protected, no rulesets. Teammates cannot push because the repo belongs to a personal account and only the owner and invited collaborators may push.
- **Open:** Safak adds Harsh, Tarun and Adnan under Settings → Collaborators; they accept the invitation.

**Open (not done by Claude):** `plan.md`/`plan.en.md` were moved to `docs/` and `docs/todo/` was added to `.gitignore` locally; not committed yet. Links to `../plan*.md` in the architecture docs and the P1 TODO need updating after that move.
