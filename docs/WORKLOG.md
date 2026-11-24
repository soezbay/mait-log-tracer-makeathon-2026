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

### develop branch and branch rules
- **What:** Created the integration branch `develop` (from `p1/ingest`, i.e. `main` plus ingest steps 1-5) and pushed it. `AGENTS.md` §8 now says: work only on `develop` or your own `p<N>/<topic>` branch, start every task from the latest `develop`, merge back into `develop` when tests pass, never commit, merge or push to `main`; `main` is updated only by Safak from a green `develop`. Start-here list and definition of done updated accordingly.
- **Why:** `main` stays stable for the demo and the pitch while everyone integrates on `develop`.
- **Where:** `AGENTS.md`; branch `develop`.
- **Open:** optionally make `develop` the default branch and protect `main` in the GitHub settings.

### Ingest steps 6-7: normalization and writing events (P1)
- **What:**
  - `normalize/timestamps.py`: ISO text to naive UTC; times without a zone are read in `DEFAULT_TIMEZONE` and flagged `tz_assumed`.
  - `normalize/levels.py`: map to `DEBUG/INFO/WARN/ERROR/FATAL` (`Critical`/`CRITICAL` → `FATAL`); unknown levels stay `NULL`, `level_raw` keeps the original.
  - `normalize/dedupe.py`: SHA-1 fingerprint over host, event_id, UTC time and message; late detector (entry more than 60 s older than an earlier entry of the same file).
  - `storage/repositories/events.py`: PyArrow batch insert, duplicate marking in SQL (`duplicate_of` = first id with the same fingerprint), summary for the report and later `/api/stats`.
  - `ingest/full_ingest.py`: scan → parse → normalize → write; stores format, event count and checkpoint per source. `scripts/ingest.py` runs the full ingest by default.
- **Checks:** 33 tests pass (normalization, full ingest with small batches, cross-file duplicate, late entry, time-only line, repeatable rebuild), ruff clean. Real run: **1,673,792 events in 53 s**, 0 unparsed, 0 without timestamp, 11,125 duplicate events, 2,379 late, 78 with assumed time zone; all hosts in the events are known servers; `JOB-2003` chain, multi-line exception and clock-skew entry come out correctly; a per-minute error query over 24 Nov runs instantly.
- **Finding:** the `JOB-2003` chain has a fourth step: 08:30:04 `mait_win04_plm_sync` `fms/fcc` "Result upload denied for DEMO-SERVICE; permission=WRITE_DATASET" (in a `.jsonl.gz`). Plan §7 and the architecture example still show three steps.
- **Where:** `backend/src/logtracer/normalize/`, `backend/src/logtracer/ingest/full_ingest.py`, `backend/src/logtracer/storage/repositories/events.py`, tests; branch `p1/ingest`, merged into `develop`.
- **Open:** `scripts/make_fixture.py`; API endpoints `/stats`, `/sources`, `/events`, `/events/{id}`, `/events/{id}/context`.

### P1 API endpoints and fixture database
- **What:**
  - Endpoints: `GET /api/stats`, `GET /api/sources` (filters server, format, duplicates), `GET /api/events` (filters server, component, comma-separated level, from/to, text search `q`, job_id, trace_id, `include_duplicates`; `limit` ≤ 500, `offset`), `GET /api/events/{id}`, `GET /api/events/{id}/context?n=` (≤ 50 original lines around the event, read from the log file, also from `.gz`). Times are returned as ISO 8601 with `Z`.
  - `main.create_app(settings)`: one DuckDB connection per process (opened in the lifespan), a cursor per request; makes the API testable with any database.
  - `services/event_service.py`: the same functions are meant for the LLM tools of P3.
  - `scripts/make_fixture.py`: builds `data/fixture.duckdb` from the scenario files only (JOB-2001/2003/2010, INC-01 day, `import_*`): 138 files, 32,767 events in 3.3 s.
  - `contracts/examples/`: `stats.json`, `events.json` (now the real 4-step `JOB-2003` chain), `event.json`, `event_context.json` updated with real values.
  - `AGENTS.md`: P1 ownership extended by `api/sources.py`, `api/schemas.py`, `api/deps.py`, `services/event_service.py`.
- **Checks:** 40 tests pass (7 new API tests incl. filters, time window with offset, pagination, detail, context for a multi-line CSV entry and a `.gz` file, 404s), ruff clean. Live on the real database: all endpoints answer in 15–95 ms.
- **Where:** `backend/src/logtracer/api/`, `backend/src/logtracer/services/`, `backend/src/logtracer/main.py`, `backend/scripts/make_fixture.py`, `contracts/examples/`; branch `p1/ingest`, merged into `develop`.
- **Open:** day 3: checkpoints, watcher, `POST /api/ingest` + `GET /api/ingest/progress` (SSE). Demo docs still show the `JOB-2003` chain with 3 steps.

### Continuous ingest: checkpoints, watcher and /ingest API (P1, MAIT step 3)
- **What:**
  - `ingest/incremental.py`: per file the checkpoint decides: unknown → all events; grown → only entries after `checkpoint_line` (the whole file is parsed again so CSV headers and multi-line entries stay correct); shrunk or previously a copy → its events are replaced; byte-identical to another file → duplicate; only touched → skipped. Event duplicates are flagged for the new ids only. Deleted files keep their events.
  - `ingest/event_writer.py`: row building shared by full and incremental ingest.
  - `services/ingest_service.py`: one ingest at a time in a background thread through a cursor of the single DuckDB connection; changes arriving during a run are queued; progress is pushed to SSE subscribers.
  - `ingest/watcher.py`: watchdog observer with debounce. **Safety net** `WATCH_RESCAN_S` (default 10 s): a quiet size/mtime check of the whole package, because in the live test Windows delivered change notifications for shell appends late or not at all. Watcher and rescan runs stay silent when nothing changed.
  - API: `POST /api/ingest` (`full` | `incremental`, 202 / 409), `GET /api/ingest/status`, `GET /api/ingest/progress` (SSE: `state`, `started`, `progress`, `new_file`, `done`, `error`).
  - Contract examples `ingest_status.json` and `ingest_progress.sse.txt`; `AGENTS.md` ownership extended.
- **Checks:** 51 tests pass (new file, append, CSV append keeps header mapping, rewrite, copy, cross-file duplicate, watcher, manager events, quiet rescan, endpoints), ruff clean. Live on a temporary copy of scenario files (original package untouched): new `.txt` and `.gz` files and four shell appends each became queryable in about 5 s; the SSE stream showed `new_file` and `done`; a line that the watcher had missed earlier was picked up by the rescan.
- **Where:** `backend/src/logtracer/ingest/`, `backend/src/logtracer/services/ingest_service.py`, `backend/src/logtracer/api/ingest.py`, `backend/src/logtracer/main.py`, `backend/.env.example`, `contracts/examples/`; branch `p1/ingest`, merged into `develop`.
- **Open:** for the pitch demo, copy new files into a watched folder (a copy of the package or a separate demo folder), never edit the original package.

### Log package via Git LFS with download and extraction on start (P1)
- **What:**
  - `MAIT_Makeathon_Logpaket.zip` (83 MB, 13,836 files) is tracked with Git LFS (`.gitattributes`); the extracted folder stays git-ignored.
  - `core/logpaket.py`, called on every program start (API lifespan, `scripts/ingest.py`, `scripts/make_fixture.py`):
    - ZIP missing or only an LFS pointer → `git lfs pull --include <zip>` (`AUTO_DOWNLOAD`, uses the same Git login as push, so it works for a private repo).
    - Marker `data/logpaket.extracted.json` matches the ZIP (size + mtime) → nothing to do.
    - Otherwise → extract only missing or different files (`AUTO_EXTRACT`); existing files are never rewritten; entries with `..`, absolute paths or drive letters are rejected (zip slip).
  - Settings `LOGPAKET_ZIP`, `AUTO_EXTRACT`, `AUTO_DOWNLOAD` in `config.py` and `.env.example`; `AGENTS.md` (layout, setup) and `backend/README.md` updated.
- **Why:** Everyone gets the same log package with `git clone` and a program start, without putting 867 MB of files into normal Git history.
- **Checks:** 60 tests pass (first extraction, fast second start, repair of a missing file without touching others, new ZIP version, LFS pointer, download then extract, failed download message, missing ZIP with existing folder, zip slip), ruff clean. Real ZIP: existing folder fully compared in 1.25 s, next start 0.00 s; fresh extraction of all 13,836 files in 50 s, content identical to the original.
- **Where:** `.gitattributes`, `MAIT_Makeathon_Logpaket.zip`, `backend/src/logtracer/core/logpaket.py`, `backend/tests/test_logpaket.py`; branch `p1/ingest`.
- **Open:** not pushed yet. The repo is still public, and an LFS object in a public repo can be downloaded by anyone. Push after the repo is private. Free GitHub LFS quota is about 1 GB storage and 1 GB download per month (≈ 12 clones of the ZIP).

### Deferred decision: hosting of the log package
- **What:** New section §17 "Deferred decisions" in `docs/plan.en.md` and `docs/plan.md` with D1: where the log package ZIP lives. Lists options A (whole repo private), B (separate private data repo), C (release asset in a private repo), D (cloud storage) with effort, a recommendation and the question to the organizers about redistribution.
- **Why:** On GitHub, Git LFS files have the same visibility as the repo; they cannot be made private on their own. The team wants to decide later, so the LFS commit stays unpushed until then.
- **Where:** `docs/plan.en.md` §17, `docs/plan.md` §17
- **Open:** team decision; then push `87bfd44` (option A) or rebuild the download for the chosen option.

**Open (not done by Claude):** `plan.md`/`plan.en.md` were moved to `docs/` and `docs/todo/` was added to `.gitignore` locally; not committed yet. Links to `../plan*.md` in the architecture docs and the P1 TODO need updating after that move.
