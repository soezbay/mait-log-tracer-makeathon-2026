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

**Open (not done by Claude):** `plan.md`/`plan.en.md` were moved to `docs/` and `docs/todo/` was added to `.gitignore` locally; not committed yet. Links to `../plan*.md` in the architecture docs and the P1 TODO need updating after that move.

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
