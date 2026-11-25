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

### JOB-2003 demo chain corrected to 4 steps
- **What:** Plan §7 (EN + DE) and the example assistant answer in `ARCHITECTURE.md`/`ARCHITEKTUR.md` §5 now show the full chain from the data: win03 `converter/nx_jt` SUCCESS 08:30:00 → win04 `fms/fcc` "Result upload denied for DEMO-SERVICE; permission=WRITE_DATASET" 08:30:04 → linux1 `fms/fsc` upload rejected 08:30:08 → linux1 `teamcenter/workflow` publish failed 08:30:12. The example answer got the extra step, evidence line (`mait_win04_plm_sync/logs/fms/fcc/creative_2026-11-24.jsonl.gz`, line 29), affected system and the service user in summary, uncertainty and verification steps.
- **Why:** The docs showed only 3 steps on 2 servers; the ingest showed 4 steps on 3 servers. Pitch, assistant prompt tests and evaluation ground truth must match the data.
- **Where:** `docs/plan.en.md`, `docs/plan.md`, `docs/ARCHITECTURE.md`, `docs/ARCHITEKTUR.md`
- **Also:** Safak invited Harsh, Tarun and Adnan as GitHub collaborators.

### Push incl. the log package ZIP; main updated
- **What:** Pushed `p1/ingest` and `develop`. `main` had two pull requests the team merged directly into it (#1 P4 frontend integration, #2 P2 analysis integration); merged `origin/main` into `develop` (conflict only in `docs/AI_LOG.md`, both sides kept), then set `main` to `develop` and pushed both. This includes the Git LFS ZIP (`87bfd44`), uploaded to the repo while it is still public. Plan §17 D1 status updated.
- **Why:** Safak decided to push everything now, knowing the repo is public; he owns `main` and asked for the merge.
- **Open:** D1 (private repo or separate data repo) is still open; until the repo is private the ZIP can be downloaded by anyone.

### Remove IDE settings from Git
- **What:** `git rm --cached -r .idea/` (6 JetBrains files that came in with the merged PRs); `.gitignore` now ignores `.idea/`, `.vscode/` and `data/`.
- **Why:** IDE settings are personal and cause needless conflicts; `data/` only holds derived files (DuckDB, extraction marker) that are rebuilt by script. Note: pulling this commit deletes the local `.idea/` folder once (Git removes files that a pulled commit stops tracking); JetBrains IDEs recreate it on the next start, and from then on it stays untracked.
- **Where:** `.gitignore`

### Decision: main stays the default branch
- **What:** `main` remains the GitHub default branch (Safak). `AGENTS.md` §8 now says to set the base branch to `develop` when opening a pull request.
- **Why:** PRs #1 and #2 went into `main` because GitHub targets the default branch; the rule makes the base choice explicit.
- **Where:** `AGENTS.md` §8

### Branch model: only main
- **What:** Merged `develop` into `main` (contents were identical apart from one PR merge commit), then deleted `develop` locally and on GitHub. `AGENTS.md` §1, §8 and §10 now say: `main` is the only shared branch; small changes are committed on `main`, bigger ones on a short-lived `p<N>/<topic>` branch that is merged back into `main` the same day; `pytest` + `ruff check`, then `git pull --rebase` before every push; no force push.
- **Why:** Safak's decision. Two long-lived branches caused PRs to land in the wrong one (#1, #2 into `main`, #4 `develop` into `main`) and extra merges.
- **Where:** `AGENTS.md`
- **Open:** teammates run `git switch main`, `git pull`, `git fetch --prune`; anyone with local work on `develop` merges it into `main` first. `frontend/README.md` (P4) still mentions `develop`.

### One-command start for backend + frontend
- **What:** `dev.cmd` in the repo root (calls `scripts/dev.ps1` with the execution policy bypassed). `.\dev` checks Python, uv and Node, creates `backend/.env` from the example if missing, runs `npm install --no-package-lock` on the first run, refuses to start if port 8000 or 5173 is busy, starts the backend, waits for `/api/health` (up to 5 min, first start may extract the log package), then starts Vite and opens the browser. Ctrl+C (or one side exiting) stops both process trees. Options `-NoBrowser`, `-Install`. `.gitattributes` keeps `*.cmd`/`*.ps1` in CRLF.
- **Why:** Starting two servers in two terminals was error-prone for the team and for the demo.
- **Where:** `dev.cmd`, `scripts/dev.ps1`, `.gitattributes`, `AGENTS.md` §3, §6
- **Checks:** started twice from PowerShell: backend healthy, frontend 200, `/api/stats` through the Vite proxy returns the real numbers, no proxy errors with the new start order, both ports free after stopping.

**Open (not done by Claude):** `plan.md`/`plan.en.md` were moved to `docs/` and `docs/todo/` was added to `.gitignore` locally; not committed yet. Links to `../plan*.md` in the architecture docs and the P1 TODO need updating after that move.

### Frontend API contract binding
- **What:** Fast-forwarded `main` to `7f3e3d5`; kept the proxy on `http://localhost:8000`, made Live the default, and normalized the frontend against the frozen API examples (`limit/offset`, stats fields, `source_path`, and context line `no`). Kept JOB-2003, JOB-2010 and the recovered retry separate in the demo.
- **Why:** Make the P4 frontend consume the shared backend contract while the backend routes are being implemented.
- **Where:** `frontend/vite.config.mjs`, `frontend/.env.example`, `frontend/src/api.ts`, `frontend/src/main.tsx`, `frontend/src/demo.ts`, `frontend/src/incident.ts`, `frontend/README.md`, `docs/AI_LOG.md`.
- **Checks:** TypeScript check and Vite production build passed. `localhost:8000` did not accept a connection.
- **Open (at the time of this entry):** The checkout then registered only `GET /api/health`. The later develop merge below added P1 stats, sources, events and context routes.

### Frontend branch synced with develop
- **What:** Merged the latest `origin/develop` (`cb794f2`) into the frontend branch. The branch now includes P1 stats, sources, event and source-context APIs plus the fixture database builder. Opened the built frontend in Demo mode at `http://127.0.0.1:4173/`.
- **Why:** Bring the frontend branch up to date with the team's integration work and make the UI reviewable without a running backend.
- **Where:** Backend/API and fixture files from `develop`, updated project logs; branch `codex/frontend-backend-integration`.
- **Checks:** Static preview returned HTTP 200 and the Demo dashboard loaded in the browser. Automated tests were not run.
- **Open:** `localhost:8000` did not respond here. P2 groups/trace routes are not in `develop`; P3 chat exists on a separate branch and still needs integration.

### Frontend README reflects merged backend APIs
- **What:** Updated the frontend setup notes to distinguish P1 endpoints now included in the branch from P2 groups/trace routes still missing in `develop` and the P3 chat endpoint still on its separate branch.
- **Why:** Keep the API status and live setup instructions accurate after syncing with `develop`.
- **Where:** `frontend/README.md`, `docs/WORKLOG.md`, `docs/AI_LOG.md`.
- **Checks:** Reviewed the current router registrations and branch contents; no automated tests run.
- **Open:** Start the backend with its fixture database and integrate P2/P3 routes before all Live screens work.

### English and German language settings
- **What:** Added English and German UI translations, with English as the default. The Settings control stays at the bottom of the desktop sidebar and floats at the bottom left on narrow screens; the choice persists in browser storage. The ZIP picker uses a translated button instead of the browser's native-language label.
- **Why:** Let users use the frontend in English by default or switch to German from anywhere in the app.
- **Where:** `frontend/src/i18n.tsx`, `frontend/src/main.tsx`, `frontend/src/style.css`, `frontend/src/ProcessMonitor.tsx`, `frontend/src/IncidentDetail.tsx`, `frontend/src/api.ts`, `frontend/src/demo.ts`, `frontend/src/import-zip.ts`, `frontend/src/incident.ts`, `frontend/README.md`; commit `self`.
- **Checks:** TypeScript `--noEmit` and Vite production build passed. Checked the responsive Demo preview; Vite reports existing dependency `use client` warnings. No automated tests run.
- **Open:** During preview, Live `/stats` and `/events` requests returned HTTP 500. P2 groups/trace and P3 chat routes are still absent from `develop` and need integration for full Live functionality.

### Compact page layout and centered headings
- **What:** Reduced main page padding, card spacing, notice height and heading/metric type sizes. Centered page headings and their descriptions, with a comfortable description width on large screens.
- **Why:** Make the dashboard and other screens less oversized while keeping the page hierarchy easy to scan.
- **Where:** `frontend/src/style.css`, `docs/AI_LOG.md`, `docs/WORKLOG.md`; commit `self`.
- **Checks:** TypeScript `--noEmit` and Vite production build passed.
- **Open:** -

### Smaller dashboard content
- **What:** Reduced card and notice padding, form control and body-copy sizes, table cell spacing, and metric values. Kept the page heading and its centered alignment unchanged.
- **Why:** Make the dashboard content more compact while preserving the heading treatment the user approved.
- **Where:** `frontend/src/style.css`, `docs/AI_LOG.md`, `docs/WORKLOG.md`; commit `self`.
- **Checks:** TypeScript `--noEmit` and Vite production build passed.
- **Open:** -

### Validate timeline date filter values
- **What:** Restrict `from` and `to` query values to valid four-digit `datetime-local` values. Invalid dates, including years with extra digits, now display empty and are omitted from the API query.
- **Why:** Prevent malformed URL dates from rendering as impossible years in the browser's UTC date controls.
- **Where:** `frontend/src/main.tsx`, `docs/AI_LOG.md`, `docs/WORKLOG.md`; commit `self`.
- **Checks:** TypeScript `--noEmit` and Vite production build passed.
- **Open:** -

### Limit date filters to the current time
- **What:** Set a dynamic `max` on both timeline date/time controls and reject URL or typed values after the current UTC minute. Future values are omitted from the API query.
- **Why:** Prevent selecting a date or time in the future.
- **Where:** `frontend/src/main.tsx`, `docs/AI_LOG.md`, `docs/WORKLOG.md`; commit `self`.
- **Checks:** TypeScript `--noEmit` and Vite production build passed. In the preview, a five-digit-year query rendered blank and the date control exposed the current UTC minute as its maximum.
- **Open:** -

### Apply the UTC date limit to the process monitor
- **What:** Moved date/time validation into a shared frontend helper and applied the same current UTC minute maximum to both process monitor filters. Out-of-range values are excluded from process results.
- **Why:** Keep date filtering consistent between the process monitor and event timeline when investigating logs from multiple systems.
- **Where:** `frontend/src/time.ts`, `frontend/src/main.tsx`, `frontend/src/ProcessMonitor.tsx`, `docs/AI_LOG.md`, `docs/WORKLOG.md`; commit `self`.
- **Checks:** TypeScript `--noEmit` and Vite production build passed. Preview showed the current UTC maximum on both fields; a forced future value was marked invalid and did not filter the demo results.
- **Open:** -

### Add confirmation to process monitor filters
- **What:** Added an Apply filters button so process-monitor changes remain pending until confirmed. The To date now has From as its minimum; moving From later clears any earlier To value. The current UTC maximum remains active.
- **Why:** Make filter changes explicit and prevent reversed date ranges.
- **Where:** `frontend/src/ProcessMonitor.tsx`, `frontend/src/i18n.tsx`, `frontend/src/style.css`, `docs/AI_LOG.md`, `docs/WORKLOG.md`; commit `self`.
- **Checks:** TypeScript `--noEmit` and Vite production build passed. In the preview, setting From to 10:00 set To's minimum to 10:00; an earlier To value was cleared. Apply filters reduced the demo list from three jobs to two.
- **Open:** -

### Use browser-local time in date filters
- **What:** Date/time inputs now use the browser's local wall clock and show the corresponding time zone. Timeline URL values stay canonical UTC timestamps; API filters convert local input to UTC. Process-monitor comparisons convert local boundaries to UTC instants and keep the current-time and To-after-From rules.
- **Why:** `datetime-local` controls accept local wall-clock values. Treating them as UTC shifted selections by the browser's UTC offset, so the chosen log time could be an hour off.
- **Where:** `frontend/src/time.ts`, `frontend/src/main.tsx`, `frontend/src/ProcessMonitor.tsx`, `frontend/src/i18n.tsx`, `docs/AI_LOG.md`, `docs/WORKLOG.md`; commit `self`.
- **Checks:** TypeScript `--noEmit` and Vite production build passed. Timeline parameters are converted to UTC ISO strings before API filtering.
- **Open:** -

### Pull and start the backend
- **What:** The feature branch was already current with its upstream. Installed Python 3.12.10 for the current Windows user, synced backend dependencies from `uv.lock`, and started the API in a hidden background process at `http://127.0.0.1:8000`.
- **Why:** Make the local backend available to the frontend for development.
- **Where:** Local runtime in `backend/.venv`; generated database in `data/logtracer.duckdb`; no backend source files changed.
- **Checks:** `GET /api/health` returns `status: ok` and `db_found: true`.
- **Open:** `log_root_found: false`; `MAIT_Makeathon_Logpaket/` is absent from this checkout, so the local database is empty until the log package is provided.

### Prevent duplicate assistant answers
- **What:** Kept only one assistant answer visible. Repeated normalized questions and repeated job IDs are ignored; a new question aborts an in-flight search and replaces the previous answer.
- **Why:** Avoid duplicate answer cards and requests when the same question or job is clicked again.
- **Where:** `frontend/src/main.tsx`, `docs/AI_LOG.md`, `docs/WORKLOG.md`; commit `self`.
- **Checks:** TypeScript `--noEmit` and Vite production build passed.
- **Open:** -

### Remember previously answered assistant targets
- **What:** The Assistant now remembers successfully answered normalized questions and job IDs for the current session. Reopening a previous target stays disabled after another answer replaces it; failed requests can still be retried.
- **Why:** Keep the same question or job from being opened again after switching to another answer.
- **Where:** `frontend/src/main.tsx`, `docs/AI_LOG.md`, `docs/WORKLOG.md`; commit `self`.
- **Checks:** TypeScript `--noEmit` and Vite production build passed.
- **Open:** -
### AI assistant and /api/chat (P3, Tarun)
- **What:**
  - `assistant/`: provider interface with Gemini (`google-genai`) and Claude (`anthropic`), switch with `LLM_PROVIDER`; 8 SQL tools with `LIMIT` (`get_stats`, `get_incidents`, `get_error_groups`, `get_anomalies`, `search_events`, `trace`, `correlate`, `get_context`); system prompt; answer schema (`answer.py`, interface 3); tool-use loop (`agent.py`, max 8 rounds / 14 tool calls) that ends with `submit_answer`.
  - Evidence check: every cited event id must exist and must have been returned by a tool in this conversation; `file`/`line`/`ts` always come from the database. Invalid answers are retried twice, then degraded to verified evidence with confidence <= 0.3.
  - `api/chat.py`: `POST /api/chat` streams SSE with FastAPI's built-in `fastapi.sse` (`token`, `step`, `answer`, `done`, `error`); `GET /api/chat/{conversation_id}` returns the history. Registered in `main.py` (2 lines, shared file).
  - All SQL in `assistant/data_access.py` follows `storage/schema.sql`; error group titles come from `templates.template`. Every LLM call is written to `llm_calls` with tokens, duration and cost in EUR (list prices in USD, converted with `EUR_PER_USD`, default 0.86).
  - `assistant/config.py` reads `backend/.env` and resolves `DB_PATH` against `backend/`, same rules as `core/config.py`.
  - `scripts/make_standin_db.py` builds a stand-in DB with the real schema from the log package until the full ingest exists; `scripts/ask.py` asks one question from the command line.
  - New dependencies: `google-genai`, `anthropic` (pyproject.toml, uv.lock). `GEMINI_API_KEY` added to `.env.example`; Gemini added to `docs/ARCHITECTURE.md`. Contract examples: `chat_request.json`, `chat_stream.sse`, `chat_answer.json`, `chat_history.json`.
- **Why:** P3 deliverable from plan.en.md §11: the assistant explains root causes as hypotheses with checked evidence, and the cost per question is measurable.
- **Where:** `backend/src/logtracer/assistant/`, `backend/src/logtracer/api/chat.py`, `backend/src/logtracer/main.py`, `backend/scripts/`, `backend/tests/`, `contracts/examples/`.
- **Checks:** 39 tests pass (33 new, no network, providers stubbed with real SDK types), `ruff check` clean, end-to-end check of `/api/chat` through `main.app` (stream, history, `llm_calls`, `hypotheses`).
- **Open:** Harsh to confirm the analysis table columns the tools read; Safak to share the single DB connection with `chat.configure(cursor_factory=...)`; first call against the live Gemini API; verify prices and `EUR_PER_USD` before quoting cost in the pitch; Ollama provider and `masking.py` not written.

### Readable Gemini errors (P3, Tarun)
- **What:** Gemini errors now include the HTTP code, status and Google's own message, e.g. `503 UNAVAILABLE: The model is overloaded.`, and say what to try (wait, or change `LLM_MODEL`). The retry warning shows the code too. New test for a 503 from the real `google-genai` error type.
- **Why:** The first live run against the full log package (stand-in DB: 1,666,054 events, 3,338 ERROR, 446 naive error groups) failed with only `ServerError` after 3 retries, which did not say whether Google was overloaded or rejected the request.
- **Where:** `backend/src/logtracer/assistant/providers/gemini.py`, `backend/src/logtracer/assistant/providers/base.py`, `backend/tests/test_providers_and_api.py`.
- **Checks:** 40 tests pass, `ruff check` clean.
- **Open:** rerun `scripts/ask.py` to see Google's message; first successful live Gemini answer.

### First live Gemini answer, default model gemini-3.6-flash (P3, Tarun)
- **What:**
  - First successful run against real Gemini on the stand-in DB built from the full log package. Question: "Why did the publish of JOB-2003 fail on 24 Nov?" Answer: FMS rejected the JT upload (missing write permission), confidence 0.95. Evidence matches the reference chain in ARCHITECTURE.md §5 (converter csv:31 08:30:00, FMS fsc txt:29 08:30:08, workflow jsonl:30 08:30:12) and adds the FMS client denial on mait_win04_plm_sync (fcc jsonl.gz:29, 08:30:04). The decoy `DEMO-Seal-17/C` and harmless retry ERRORs were not named. 6 tool calls, 7 LLM calls, 41,580 input + 2,948 output tokens, 152 s.
  - Default Gemini model changed from `gemini-2.5-flash` to `gemini-3.6-flash`: 2.5 is only served to keys that used it before; `gemini-3.8-flash` and `gemini-4-hydrogen` answered `503 UNAVAILABLE` (high demand) at the time of testing.
  - Cost wording: `cost_eur` is the paid-tier list price per question (the pitch metric); free-tier calls are not billed. Models without a known price show "cost unknown" until `PRICE_INPUT_PER_MTOK` / `PRICE_OUTPUT_PER_MTOK` are set.
- **Why:** New team members' keys cannot use 2.5; the default must work out of the box.
- **Where:** `backend/src/logtracer/assistant/config.py`, `costs.py`, `backend/scripts/ask.py`, `backend/.env.example`, `docs/ARCHITECTURE.md`, `contracts/examples/chat_stream.sse`.
- **Checks:** 40 tests pass, `ruff check` clean; live run as above.
- **Open:** verify gemini-3.6-flash prices and set `PRICE_*` before the pitch; 152 s per answer is too slow for a live demo (fewer rounds or lower thinking level); incidents/correlations empty until P2 delivers.

### Official price for gemini-3.6-flash (P3, Tarun)
- **What:** Added `gemini-3.6-flash` to the price table in `costs.py` from Google's pricing page (Standard, paid tier): 0.75 USD input and 3.75 USD output (incl. thinking tokens) per 1M tokens through 2026-12-31, then 1.50 / 7.50 from 2027-01-01. The JOB-2003 question (41,580 input + 2,948 output tokens) costs about 0.042 USD = 0.036 EUR on the paid tier (0.073 EUR at 2027 prices); on the free tier it is not billed. New test checks that the default Gemini model has a price.
- **Why:** The pitch metric "EUR per question" needs a cost for the default model without extra `.env` settings.
- **Where:** `backend/src/logtracer/assistant/costs.py`, `backend/tests/test_tools_and_agent.py`.
- **Checks:** 41 tests pass, `ruff check` clean.
- **Open:** switch to the 2027 prices on 2027-01-01 (or set `PRICE_*` in `.env`).

### p3/assistant brought up to date with develop (P3, Tarun)
- **What:**
  - Merged `develop` (same commit as `main`, 9e332b1: P1 ingest pipeline, API, watcher and LFS log package; P4 frontend; PR #2) into `p3/assistant`. Conflicts in `main.py`, `.env.example`, `AI_LOG.md` and `WORKLOG.md` resolved by keeping both sides.
  - `main.py`: the lifespan now passes the single DuckDB connection to the assistant with `chat.use_connection(app.state.db)` and releases it on shutdown; the chat router is registered in `create_app`. This closes the open item "share the DB connection" from the first P3 entry.
  - `.env.example`: LLM section lists `gemini` as provider and documents `GEMINI_API_KEY`. `core/config.py` (P1) gets one line, `gemini_api_key`, because `test_example_env_matches_settings` requires every key in `.env.example` to be a setting.
  - The assistant reads `LLM_MAX_TOOL_ROUNDS` and `LLM_MAX_OUTPUT_TOKENS` (names documented by P1); the output limit is passed to the Claude provider.
  - New test: starting the full app shares the DB connection with `/api/chat`, LLM calls land in that connection, and it is released on shutdown.
- **Why:** PR #3 had merge conflicts with `main`, and AGENTS.md §8 now routes all work through `develop`.
- **Where:** `backend/src/logtracer/main.py`, `api/chat.py`, `core/config.py`, `assistant/config.py`, `assistant/providers/__init__.py`, `backend/.env.example`, `backend/tests/test_providers_and_api.py`.
- **Checks:** 96 tests pass (P1 + P3), `ruff check` clean.
- **Open:** for Safak: `tests/test_incremental.py::test_manager_runs_and_publishes` is flaky, it also fails about 1 in 10 runs on a clean `main` (`state["running"]` is still True right after the `done` event).

### Groq as LLM provider (P3, Tarun)
- **What:**
  - New `GroqProvider` (`assistant/providers/groq.py`, official `groq` SDK, OpenAI-style chat completions with tool calling). `LLM_PROVIDER=groq`; default model `openai/gpt-oss-120b`, any Groq model through `LLM_MODEL` (e.g. `qwen/qwen3.8-27b`).
  - Rate limits: on 429 the provider waits as long as Groq's `retry-after` header asks (max 60 s), otherwise exponential backoff; the SDK's own retries are off so there is one retry layer. Errors show Groq's status and message (rate limit, request too large, bad key or model, server error).
  - A malformed tool call from the model (`tool_use_failed`) no longer fails the question: the agent asks the model again. `<think>` text of reasoning models is removed from the answer text.
  - Optional `LLM_REASONING_EFFORT` (`low` / `medium` / `high`) for Groq reasoning models, to trade quality for speed.
  - `ask.py --provider groq --model <id>` for comparing models from the command line.
  - `GROQ_API_KEY` and `LLM_REASONING_EFFORT` in `.env.example`; the same two settings in `core/config.py` (P1), because `test_example_env_matches_settings` requires every documented key to be a setting. New dependency `groq`.
- **Why:** Gemini 3.6 Flash answered `503 UNAVAILABLE` (high demand) in the UI after a long wait; Groq is built for low latency and lets us compare models.
- **Where:** `backend/src/logtracer/assistant/providers/groq.py`, `providers/base.py` (`with_retries` takes a `delay_for` hint), `providers/__init__.py`, `assistant/config.py`, `core/config.py`, `backend/.env.example`, `backend/scripts/ask.py`, `backend/tests/test_providers_and_api.py`, `docs/ARCHITECTURE.md`, `pyproject.toml`, `uv.lock`.
- **Checks:** 100 tests pass, `ruff check` clean. The provider was also run against the real `groq` SDK with a mock HTTP server: request shape, tool-call parsing, `retry-after` wait, `tool_use_failed` and a 401 error.
- **Open:** live comparison of `openai/gpt-oss-120b` and `qwen/qwen3.8-27b` on the real DB. Groq's docs list 8K tokens per minute for gpt-oss-120b on the developer plan while one question uses about 40-50K tokens, so it may wait for rate limits; Groq's docs do not confirm tool use for qwen3.8-27b. Groq prices are not in `costs.py` yet (set `PRICE_*` in `.env`).

### Fewer tokens per question without missing logs; counter-evidence required (P3, Tarun)
- **What:**
  - Measured on the real database (P1 ingest, 1.67 M events): the system prompt and tool definitions were 91% of the input, because every model call resends them. Tool definitions went from 5,463 to 2,771 characters (time format explained once in the prompt), `submit_answer` from 1,614 to about 700.
  - Recall fixes found while measuring: `search_events(text="JOB-2003")` returned 0 events because it only searched `message`, while the job id sits in its own field. It now searches the whole original line (`raw`) and finds all 102. `trace("JOB-2003")` showed 4 events and nothing about the 49 re-runs `JOB-2003-R01..R49` (98 more events with the same failure); it now adds `related`: the related keys and groups with counts and citable sample ids.
  - Compact results: event lists are tables (`cols` once, `rows` as lists; empty columns left out). When more events match than fit, the listed rows are different lines (max 2 per host/component/level/message pattern) and `groups` summarises ALL matches with counts, time range and sample ids, so no matching line silently disappears. The evidence check reads ids from the table format too.
  - Prompt: trace first for a named job, then follow the chain across servers; read `groups` and `related`; 2 to 5 tool calls are usually enough.
  - `counter_evidence` must not be empty: the backend sends the answer back to the model with a clear instruction (the answer format, interface 3, is unchanged).
- **Why:** On Groq's free plan (8K tokens per minute for gpt-oss-120b) one question (13.9K tokens) waited up to 47 s for rate limits, and the earlier answers missed that the failure repeated in 49 re-runs.
- **Where:** `backend/src/logtracer/assistant/data_access.py`, `tools.py`, `prompt.py`, `answer.py`, `agent.py`, `backend/tests/test_tools_and_agent.py`, `backend/tests/fixtures.py`.
- **Checks:** 104 tests pass (new: text search in the raw line, related re-runs are reported and citable, truncated results count all matches and avoid repeats, answer without counter-evidence is sent back), `ruff check` clean. Simulation of the JOB-2003 question on the real DB through the Groq provider and the agent: about 7.8K input tokens instead of 13.9K, same 4 evidence lines (csv:31, fcc jsonl.gz:29, fsc txt:29, workflow jsonl:30).
- **Open:** live run with Groq; at about 7.8K tokens a question is still close to the 8K-per-minute limit, so a second question within the same minute can wait. For Safak: `data/logpaket.extracted.json` (extraction marker) is not git-ignored and shows up in `git status`.

### Related re-runs are always reported (P3, Tarun)
- **What:** `trace` now starts with `related_summary`, a plain sentence such as "ALSO: 98 log lines of 49 OTHER jobs (JOB-2003-R01 ... JOB-2003-R49) mention JOB-2003: 49x ERROR mait_win04_plm_sync fms/fcc ...". The ToolBox remembers related jobs that logged WARN/ERROR/FATAL, and an answer that mentions none of them (no related key, no shared prefix such as JOB-2003-R, no count, no word like re-run) is sent back to the model with the facts. Related lines with only INFO do not force a mention.
- **Why:** The first live run with Groq gpt-oss-120b after the token cut (7.4 s, 3 LLM calls, 6,489 input + 1,171 output tokens, no rate-limit waits, all 4 evidence lines correct, counter-evidence present) did not mention that the same failure happened in 49 re-runs, although trace returned them in a nested table at the end.
- **Where:** `backend/src/logtracer/assistant/data_access.py`, `tools.py`, `agent.py`, `backend/tests/test_tools_and_agent.py`.
- **Checks:** 108 tests pass (4 new), `ruff check` clean. Replay on the real DB: the answer from the live run is sent back with "98 log lines of 49 other jobs"; the corrected answer is accepted with the same 4 evidence lines.
- **Open:** Groq prices for gpt-oss-120b in `costs.py`.

### Resolve frontend pull request conflicts
- **What:** Merged the latest `main` into `codex/frontend-backend-integration`. Combined the frontend entries with the P1/P3 entries in `docs/AI_LOG.md` and `docs/WORKLOG.md`, keeping the history from both branches.
- **Why:** The pull request could not merge while both branches had edits in these two append-only logs.
- **Where:** `docs/AI_LOG.md`, `docs/WORKLOG.md`; branch `codex/frontend-backend-integration`.
- **Checks:** `git diff --check` passed; no conflict markers remain.
- **Open:** Commit and push the merge, then confirm GitHub reports the pull request as mergeable.
