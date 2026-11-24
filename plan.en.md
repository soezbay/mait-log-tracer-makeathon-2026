# Makeathon Plan: AI Log Assistant for MAIT

> Working title: **Log Tracer** · Challenge: *Automated log file management with an AI assistant* (MAIT)
> Schedule: Day 1 concept, user stories & ingest · Days 2–3 build · Day 4 pitch
> German version: [plan.md](plan.md) · Architecture: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) · Data: `MAIT_Makeathon_Logpaket/` (not in Git)

---

## 1. Goal in one sentence

An assistant that **collects the logs of all servers recursively without modifying the originals**, normalizes them, **detects error groups and anomalies**, **correlates them across systems** and explains **root causes as hypotheses with evidence, uncertainty and verification steps** via chat.

## 2. What MAIT expects (per the log package README)

The log package defines a four-step frame. Our plan follows it:

| MAIT step | What we build | When |
|---|---|---|
| 1. Collect recursively, preserve the source, normalize formats & timestamps, store | Ingest pipeline → DuckDB, originals stay untouched | Day 1 afternoon |
| 2. Detect error groups & relationships, select relevant AI context, **measure quality and cost** | Templates, anomalies, correlation, LLM tools, evaluation incl. token cost | Day 2 |
| 3. Process new entries continuously, **checkpoints and deduplication** | Incremental ingest + folder watcher, dedupe at file and event level | Day 3 morning |
| 4. Visualize; explain causes as **hypotheses with evidence, uncertainty and verification steps** | UI with timeline, dependency graph, chat | Day 3 + pitch |

Explicit traps the jury will check:
- An **ERROR does not mean** the operation failed for good (there are successful retries).
- **Several ERRORs can share one cause**, so we group them instead of counting them.
- **Same job display number does not mean same job.**
- **Systems contradict each other** (e.g. converter reports `SUCCESS`, publish finds no result).
- **Incomplete evidence**: the assistant must then admit uncertainty.
- Technical: varying formats, **Windows-1252/UTF-8, gzip, multi-line exceptions, duplicate events, late entries, a skewed source clock**.

## 3. What is in the data (analysis from 2026-11-23)

**Size**
- **14 servers**: 7 Linux, 7 Windows. Layout: `<server>/logs/<application>/<component>/<file>`.
- **13,643 log files**, but only **5,068 with distinct content** (approx. 460 MB uncompressed). Many `_runNN` files are **byte-identical copies** → file-hash dedupe saves about 60 % of the work.
- **approx. 1.67 M events** (distinct files): INFO 92 %, DEBUG 79 k, WARN 46 k, **ERROR only 3,345 (0.2 %)**.
- Metadata (not logs): `server_info.json` (hostname, OS, role), `README.md` per folder.

**Servers**

| Server | OS | Role |
|---|---|---|
| `mait_linux1` | Linux | Teamcenter backend |
| `mait_linux1_teamcenter_app` | Linux | Teamcenter application |
| `mait_linux2` | Linux | Web and search (Active Workspace) |
| `mait_linux2_teamcenter_db` | Linux | Teamcenter database |
| `mait_linux3` | Linux | Gateway & infrastructure (license, T4S/T4EA, DB) |
| `mait_linux3_cad_service` | Linux | CAD service (NX, TLS, DNS) |
| `mait_linux4_dispatcher_service` | Linux | Dispatcher service |
| `mait_win01_dispatcher_master` | Windows | Dispatcher master |
| `mait_win02_dispatcher_worker` | Windows | Dispatcher worker (incl. `clock` logs) |
| `mait_win03_cad_converter` | Windows | CAD converter (NX/JT, PDF, ME10, Solid Edge) |
| `mait_win04_plm_sync` | Windows | PLM sync (incl. `imported_mixed_hosts`) |
| `mait_windows1` | Windows | Dispatcher and NX |
| `mait_windows2` | Windows | CAD and other converters |
| `mait_windows3` | Windows | Integration clients (rich client, CAD integration) |

**Formats** (all with timestamp, level, host, component, event ID, job ID, text)

| Format | Example |
|---|---|
| `.log` key=value | `2026-11-23T08:00:14Z WARN host=… component=… event_id=… job_id=… \| text` |
| `.txt` with JSON payload | `2026-11-24T08:00:37Z [WARN] host=… \| {"message": …, "duration_ms": …}` |
| `.csv` (semicolon, CRLF) | `timestamp;level;host;component;event_id;job_id;message[;duration_ms;session_id]`, **multi-line stack traces inside quotes** |
| `.jsonl` / `.jsonl.gz` | one JSON object per line; `ki-integriert` variant additionally has `trace_id` |
| `.xml` | `<Events><Event><timestamp>…</timestamp>…</Event></Events>` (demo format, not EVTX) |
| `import_*.log` | `2026-10-06 14:02:15.234 [INFO] …` or **time only** `[14:02:15] TC.RAC - …` (derive the date from context) |

Specifics: 1 file in Windows-1252, CRLF in Windows files, timestamps almost everywhere ISO-8601 UTC (`…Z`).

**Time ranges & data sets**
- **2026-10-01 to 10-30** (`*.ki-integriert.jsonl`): a month of operation with `trace_id` and **tagged incidents `INC-01` … `INC-10`** (e.g. "Downstream timeout/retry during INC-01; dependency=mait_linux2_teamcenter_db").
- **2026-10-06** (`import_*.log`): imported free-text error scenarios (jobs 4710/4711, converter, license, workflow).
- **2026-11-23**: mostly normal operation (`NORMAL-…` jobs), used as the baseline. It also contains a few failing jobs (`JOB-1xxx`, e.g. `JOB-1003` "No output JT produced" on `mait_windows2`), which must be excluded from the baseline.
- **2026-11-24** (`creative_*`): targeted error scenarios in all formats.

**Correlation keys**: `job_id`, `trace_id`, `session_id`, `event_id`, `INC-xx`, `dependency=<host>`, object IDs (`DEMO-…`, `DEMO-Seal-17/C`), request IDs (`REQ-…`).

**Error patterns found (candidates for demo & evaluation)**
- Downstream timeouts with a dependency on the Teamcenter DB or the dispatcher master (`INC-01…10`)
- "Worker failed … **local clock is behind**" → skewed source clock (`mait_win02_dispatcher_worker`, `dispatcher/module`, `JOB-2001`). The entry itself carries `clock_offset_seconds: -94` and an `observed_at` time, so the offset can be measured instead of guessed.
- **Converter reports SUCCESS, publish finds no result** (`JOB-2003`) → contradicting systems; the actual cause is a rejected FMS upload (missing write permission on the target volume), see §7
- **Missing assembly reference** `DEMO-Seal-17/C` (`JOB-2010`) → "Reference target absent" (Teamcenter SOA) → "Export aborted" (NX/JT converter), plus a multi-line Java exception
- "No output JT produced" (`JOB-1003`, Solid Edge → JT translator on `mait_windows2`, 23 Nov): a separate case, not linked to `DEMO-Seal-17/C`
- `no space left on device` when writing the result
- Access denied (reading share, writing PDF, `WRITE_DATASET`)
- Process killed due to **memory pressure** (large assembly)
- **Cached endpoint** → connection refused (DNS/cache)
- Search/indexer unavailable
- ERP: cyclic product structure, supplier block → "upstream dependency failure" chains
- Dispatcher queue saturation
- **Traps**: ERROR level on harmless messages ("Transient retry recovered", "Cache lookup successful").

> Missing docs: the README references `_dokumentation/FORMATE.md` and `INTEGRATION.md`, which are not in the package (time zones, limits, T4S/T4EA terminology). **Ask the mentor on day 1.**

## 4. Relevance to MAIT (for concept & pitch)

- MAIT: IT service provider for manufacturing SMEs. **PLM, CAD/CAM, ERP, managed services** (partners incl. Siemens, PTC, SAP-PLM, abas, Comarch).
- The data mirrors exactly such a landscape: **Teamcenter, Active Workspace, Dispatcher, NX/Solid Edge/ME10 converters, FMS, T4S/T4EA (ERP gateway), license service**.
- **Lever = managed services**: supporters search manually across 14 servers and several formats today. Every minute saved in root-cause analysis scales across thousands of customers.
- **Differentiation**: hackaTUM 2023 (Rohde & Schwarz, e.g. "Logzilla") let you upload and query *one* file. **We: 14 servers, cross-system correlation, hypotheses with evidence, uncertainty and verification steps, measured quality and cost.**

## 5. Personas

1. **Sandra, supporter in MAIT managed services**: ticket "JT conversion for assembly X failed". Wants to know in < 5 minutes *where* the cause is and *what to check*.
2. **Tobias, system engineer at the customer**: wants to know whether a problem recurs and which systems depend on each other.
3. **Managed services team lead**: overview of abnormal servers and open incidents.

## 6. User stories (MVP = must, rest = could)

**Must**
- US1: As a supporter I want **all logs in a folder to be ingested recursively**, regardless of format or encoding. The originals stay untouched.
- US2: As a supporter I want to see all events on **one shared timeline**, filtered by server, component, level and job/trace.
- US3: As a supporter I want to see **error groups instead of single ERRORs**: what shares the same cause, what recovered via retry?
- US4: As a supporter I want to ask in chat "**Why did the JT conversion fail on 24 Nov?**" and get a **hypothesis with causal chain, affected systems, evidence lines, uncertainty and verification steps**.
- US5: As a supporter I want to click on a piece of evidence and see the **original line in the original file** with context.
- US6: As an operator I want **new log files to be picked up automatically** (checkpoint), **without duplicates**.

**Could**
- US7: Export an incident/ticket summary as a draft.
- US8: "Has this happened before?": find similar error groups from October.
- US9: Dependency graph of the servers (from `dependency=…` and correlations).
- US10: Teach a new log format from sample lines (LLM proposes a parser profile).
- US11: "Quality & cost" dashboard (hit rate, tokens, € per question).

## 7. Demo scenario

**Pick it from the real data on day 1.** Favorites, because they show the jury's traps:

1. **"Publish fails although the converter reports SUCCESS"** (24 Nov, `JOB-2003`, verified in the data):
   - 08:30:00 `mait_win03_cad_converter` `converter/nx_jt`: "Conversion succeeded; JT output=DEMO-301.jt"
   - 08:30:08 `mait_linux1_teamcenter_app` `fms/fsc`: "Upload rejected; access policy lacks target volume write permission"
   - 08:30:12 `mait_linux1_teamcenter_app` `teamcenter/workflow`: "Publish task failed: no registered result; converter status=SUCCESS"

   Cause: missing write permission on the FMS volume, not the converter. Shows **contradicting systems** across 2 servers and 3 formats (CSV, TXT, JSONL).
2. **Missing assembly reference** (24 Nov, `JOB-2010`): `nx/batch` "Required child DEMO-Seal-17/C not resolved" → `teamcenter/soa` "Reference target absent from exported input package" → `converter/nx_jt` "Export aborted because required reference is missing". A **multi-line Java exception** with the same job number follows at 11:01; check whether it belongs to the same job (the README warns that equal display numbers do not always mean the same job).
3. **`INC-01` in October**: the Teamcenter app repeatedly reports downstream timeouts to `teamcenter_db`. Many ERRORs, **one cause**, partly successful retries. Shows **grouping + retry ≠ failure**.
4. **"Worker failed, local clock is behind"** (`mait_win02_dispatcher_worker`, `JOB-2001`): shows **source clock correction** (`clock_offset_seconds: -94`). Without it, the order of the chain is wrong.

Plus a **red herring**: harmless ERRORs ("Transient retry recovered") are *not* named as the cause.

## 8. Architecture

```
 MAIT_Makeathon_Logpaket/  (read only)
        │ recursive scan · hash · encoding · gzip in memory
        ▼
 ┌──────────────┐  ┌──────────────┐  ┌─────────────┐  ┌──────────────┐  ┌──────────────┐
 │ Format       │─▶│ Normalizer   │─▶│ Dedupe &    │─▶│ Templates    │─▶│ Error groups │
 │ detection &  │  │ UTC, level,  │  │ checkpoint  │  │ (Drain3)     │  │ anomalies,   │
 │ parsers (6)  │  │ clock fix    │  │             │  │              │  │ correlation  │
 └──────────────┘  └──────────────┘  └─────────────┘  └──────────────┘  └──────┬───────┘
                                  ▼                                               │
                           ┌──────────────┐  tools (SQL)   ┌──────────────────┐   │
                           │ DuckDB       │◀──────────────│ AI assistant     │◀──┘
                           │ logtracer.duckdb│               │ LLM + tool use   │
                           └──────────────┘               └────────┬─────────┘
                                                                   ▼
                     UI: timeline · error groups · dependency graph · chat with evidence
```

### Principle: originals stay untouched

Log files are **read only**. Everything derived lives in **one DuckDB file** (`data/logtracer.duckdb`) that a script can rebuild at any time. Every event points back to its original file and line.

### Data model (DuckDB)

**`sources`**: one row per file

| Field | Description |
|---|---|
| `source_id`, `path` | relative path within the log package |
| `server`, `os`, `role` | from folder + `server_info.json` |
| `application`, `component` | from `logs/<application>/<component>` |
| `format`, `encoding`, `compressed` | detected on read |
| `sha256`, `size`, `mtime` | for file dedupe |
| `duplicate_of` | reference if byte-identical copy |
| `checkpoint_bytes`, `checkpoint_line`, `ingested_at` | for incremental loading |

**`events`**: one event per (possibly multi-line) log entry

| Field | Description |
|---|---|
| `id` | internal ID (evidence reference) |
| `source_id`, `line_start`, `line_end` | link back to the original |
| `ts_raw`, `ts_utc`, `clock_offset_s` | original time, corrected UTC time, applied correction |
| `ingest_seq` | ingest order, to detect late entries |
| `host`, `component`, `level` | `level` normalized: `DEBUG/INFO/WARN/ERROR/FATAL` |
| `event_id`, `job_id`, `trace_id`, `session_id` | correlation keys |
| `message`, `attrs` (JSON) | text + extra fields (`duration_ms`, `dependency`, `object` …) |
| `template_id` | from Drain3 |
| `fingerprint`, `duplicate_of` | event dedupe |
| `raw` | original text |

Further tables: `templates`, `error_groups` (group with a shared cause, with retry status), `anomalies`, `hypotheses` (stored answers for evaluation), `llm_calls` (tokens, duration, cost).

### Components in detail

1. **Collect & parse**
   - Recurse over all servers, handle metadata (`README.md`, `server_info.json`) separately.
   - File hash before parsing → byte-identical copies (`_runNN`) are only linked, not re-parsed.
   - Encoding: UTF-8, fallback Windows-1252; decompress `.gz` in memory.
   - 6 parsers: `kv_log`, `bracket_json_txt`, `csv_semicolon` (with the `csv` module because of multi-line fields), `jsonl`, `xml_events`, `import_freetext` (incl. time-only lines).
   - Continuation lines without a timestamp (stack traces) are attached to the previous event.
2. **Normalize**: time → UTC; level mapping (`Critical/CRITICAL/SEVERE` → `FATAL`, `WARNING` → `WARN` …); **clock correction** per host when detected (`clock_offset` in messages or a systematic offset to partners via shared `job_id`/`trace_id`).
3. **Deduplicate**
   - File level: same hash.
   - Event level: same fingerprint from `host + event_id + ts_utc + message`. Duplicates are flagged, not deleted.
   - Late entries: `ts_utc` clearly before the last event of the same source → flag.
4. **Templates & error groups**: Drain3 on `message`. Group = same template + same component + temporal proximity. Each group gets a status: **"recovered"** (retry succeeded) or **"finally failed"**.
5. **Anomalies**: error rate per server and minute vs. the baseline from 23 Nov / October (z-score), new/rare templates, level jumps, duration outliers (`duration_ms`).
6. **Correlation**
   - Hard links: same `trace_id`, `job_id` (+ host/time window, since same number ≠ same job), `session_id`, object ID, `INC-xx`.
   - Soft links: temporal proximity of error groups across servers, ordering, `dependency=<host>`.
   - Result: **hypothesis** = causal chain + confidence + counter-evidence.
7. **AI assistant**: LLM with tool use. It never reads all logs, it selects context deliberately (MAIT step 2):
   - `search_events(server, component, level, time_range, text)`
   - `get_error_groups(time_range)` · `get_anomalies(time_range)`
   - `trace(job_id | trace_id | object_id)`: all events of one chain across servers
   - `correlate(group_id)` · `get_context(event_id, ±n)`
   - **Answer format (mandatory)**: summary · causal chain · affected servers/components · evidence `[server | file:line | time]` · **uncertainty & counter-evidence** · **verification steps** · recommendation.
8. **Continuous (day 3)**: watcher on the log folder. A new file or appended lines are read from the checkpoint, deduplicated and shown in the UI. Demo: copy a file into the folder during the pitch.
9. **UI**: timeline per server, error group list, dependency graph, chat with clickable evidence, "quality & cost" tile.

### Measuring quality & cost

- **Test questions** (approx. 10–15) from known scenarios: `INC-01…10`, `creative_*` scenarios from 24 Nov, `import_*` scenarios from 6 Oct.
- **Ground truth** per question: expected cause, expected servers, expected evidence.
- **Metrics**: cause correct (yes/partly/no), evidence hit rate, wrong causes (e.g. harmless ERRORs), response time, **tokens and € per question**.
- Compare "whole logs into the LLM" vs. "tool-based context selection", the strongest cost argument in the pitch.

### Tech stack

| Area | Choice | Why |
|---|---|---|
| Language | Python 3.11+ | parsing, ML, LLM SDKs in one place |
| Storage | DuckDB | single file, fast, SQL for tools |
| Template mining | Drain3 | standard for log parsing |
| Analysis | pandas, scikit-learn | simple & explainable |
| Graph | networkx (+ pyvis/Plotly) | dependency graph |
| Watcher | watchdog | monitor the folder |
| LLM | Claude API (tool use); Ollama as "local" option | demo quality; privacy argument |
| Backend / API | FastAPI + Uvicorn, Pydantic, FastAPI's built-in SSE (`fastapi.sse`) | clear interface, OpenAPI docs, live streaming |
| Frontend | React 19 + TypeScript (Vite), Mantine, ECharts, Cytoscape.js; Node.js 22 or 24 LTS; fallback Streamlit | separated from the backend, only via the API |

Details on all frameworks and components: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## 9. Repo structure (target)

```
makeathon/
├── plan.md / plan.en.md
├── docs/ARCHITEKTUR.md · ARCHITECTURE.md
├── MAIT_Makeathon_Logpaket/   # original data, read only, in .gitignore
├── data/logtracer.duckdb        # derived, in .gitignore
├── eval/questions.yaml        # test questions + ground truth
├── contracts/examples/        # one JSON example response per API endpoint (frozen interface)
├── backend/                   # Python + FastAPI
│   └── src/logtracer/
│       ├── api/               # REST + SSE endpoints
│       ├── services/          # application logic (used by API and LLM tools)
│       ├── ingest/            # scan, format detection, parsers, checkpoints, watcher
│       ├── normalize/         # time, level, clock correction, dedupe
│       ├── analysis/          # templates, error groups, anomalies, correlation, graph
│       ├── assistant/         # LLM providers, tools, prompt, answer format, cost
│       └── storage/           # DuckDB, schema, repositories
└── frontend/                  # React + TypeScript (Vite)
    └── src/                   # api/, pages/, components/, hooks/
```

## 10. Schedule

### Day 1: Concept, user stories & ingest
| Time | What | Outcome |
|---|---|---|
| Morning | Briefing, questions for the mentor (§13), request missing docs | clarity on data & judging |
| | Personas, user stories, MVP cut; **pick the demo scenario from §7** | prioritized backlog, demo case |
| Midday | Assign the 5 roles (§11); **freeze the three interfaces by 13:00** (DB schema, API contract with example JSONs, answer format) | frozen interfaces, tasks |
| Afternoon | Scanner + file dedupe + 6 parsers + writing to DuckDB | **Milestone: everything in DuckDB** |
| Evening | Sanity check (events per server, level distribution); draft test questions + ground truth | `eval/questions.yaml` v1 |

### Day 2: Analysis & assistant (MAIT step 2)
| Time | What |
|---|---|
| Morning | Drain3 templates, error groups with retry status, anomalies, clock correction |
| Afternoon | Correlation (`trace`/`job`/time window), LLM tools, answer format, cost logging |
| Evening | **Milestone: demo question end-to-end + first evaluation run with numbers** |

### Day 3: Continuous, UI, pitch (MAIT steps 3 + 4)
| Time | What |
|---|---|
| Morning | Incremental ingest with checkpoints, event dedupe, watcher; UI: timeline, error groups, chat with evidence |
| Midday | Dependency graph, quality & cost tile, improve the prompt based on evaluation |
| Afternoon | **Feature freeze 16:00**; final evaluation run, demo script, slides, backup video |
| Evening | Dress rehearsal, Q&A practice |

### Day 4: Pitch day
- Morning: final run-through, DuckDB pre-built, backup video ready
- Deliver the pitch, answer questions

## 11. Roles & work split (5 people)

**Principle:** every person owns a vertical slice, from the database up to their API endpoint, with **their own folders**. People can work independently because **three interfaces are frozen on day 1 by 13:00**, and everyone uses **stand-in data** until the real parts of the others are ready.

### Roles

| # | Person | Role | Tag | Responsibility | Owned folders/files |
|---|---|---|---|---|---|
| **P1** | Safak | **Ingest & storage** | [ING] | backend skeleton, scanner, reader, 6 parsers, normalization (time, level, dedupe), DuckDB schema, checkpoints, watcher; API `/ingest`, `/sources`, `/events`, `/stats`; fixture script | `backend/src/logtracer/ingest/`, `normalize/` (except `clock.py`), `storage/`, `api/ingest.py`, `api/events.py`, `scripts/ingest.py`, `scripts/make_fixture.py` |
| **P2** | Harsh | **Analysis & correlation** | [ANA] | Drain3, error groups (recovered/failed), anomalies, clock correction, correlation, incidents, graph; API `/analysis/*`, `/trace` | `analysis/`, `normalize/clock.py`, `api/analysis.py` |
| **P3** | Tarun | **AI assistant** | [AI] | LLM providers, tools, prompt, answer schema with evidence validation, tool-use loop, cost logging, optional summary of the top incidents; API `/chat` (SSE) | `assistant/`, `api/chat.py` |
| **P4** | Adnan | **Frontend** | [FE] | all pages and components: overview, timeline, error groups, graph, chat, source view, quality & cost; mock API | `frontend/` |
| **P5** | *open* | **Data, evaluation & pitch** | [EVAL] | mentor questions, trace the demo scenario in the logs, test questions with ground truth, evaluation script, metrics, slides, demo script, backup video, README | `eval/`, `scripts/evaluate.py`, `api/eval.py`, `docs/`, `README.md` |

P5 matters because without someone who understands the data in depth there is no ground truth to measure against and no convincing demo. P5 can start immediately, without anyone else's code.

**P5 is not assigned yet.** Until it is, the P5 tasks are split as a fallback: test questions and ground truth go to Tarun (P3) and Harsh (P2), since they need them first; slides, demo script and README go to Adnan (P4) from day 3 noon; the dress rehearsal is led by Safak (P1).

### The three interfaces (freeze on day 1 by 13:00)

| Interface | Content | Owner | Used by |
|---|---|---|---|
| **1. DB schema** `storage/schema.sql` | tables `sources`, `events`, plus the analysis tables from the start: `templates`, `error_groups`, `group_members`, `correlations`, `incidents`, `hypotheses`, `llm_calls` | P1 writes, P2 confirms the analysis tables | P2, P3 |
| **2. API contract** | endpoints from `docs/ARCHITECTURE.md` §5 plus **one JSON example response per endpoint** in `contracts/examples/` | P1–P3, each for their own endpoints | P4, P5 |
| **3. Assistant answer format** | Pydantic schema `answer.py`: summary, causal chain, evidence, uncertainty, verification steps | P3 | P4 (display), P5 (scoring) |

After that: **interface changes only after a short team agreement**, and the example JSONs in `contracts/examples/` are updated in the same commit.

### Stand-in data while others are still building

| Who | Actually waits for | Stand-in until then |
|---|---|---|
| **P1** | nothing | works directly on the log package |
| **P2** | the finished ingest from P1 | the `.jsonl` files already contain all fields: load them with `duckdb.read_json_auto()` into an `events` table that follows the schema, in a few minutes |
| **P3** | analysis tables from P2 | the same JSONL stand-in DB; a few hand-written `error_groups` rows for the demo scenario |
| **P4** | all endpoints | **mock API** from `contracts/examples/` (e.g. with MSW); later only the base URL changes |
| **P5** | `/chat` for the evaluation | work out test questions and ground truth directly from the logs; test `evaluate.py` against an example answer from interface 3 |

By day 1 evening P1 also delivers **`scripts/make_fixture.py`**, which builds a small test database from the demo scenario's files only. The DuckDB file itself stays out of Git, only the script is committed, so everyone has the same test data.

### Plan per person

| | **Day 1** | **Day 2** | **Day 3** |
|---|---|---|---|
| **P1 · Safak** | backend skeleton + `/health`; schema; scanner, reader, parsers + tests; full ingest | normalization done, dedupe; API `/events`, `/context`, `/stats`; performance | checkpoints, watcher, `/ingest` + SSE; pre-build the DB for the pitch, demo machine |
| **P2 · Harsh** | stand-in DB from JSONL; tune Drain3 masking on real messages | error groups, anomalies, clock correction, correlation; API `/analysis/*` | incidents for the overview, graph, late entries; polish together with P5 |
| **P3 · Tarun** | provider + API key; answer schema; tools against the stand-in DB | prompt, tool-use loop, evidence validation, cost; `/chat` with SSE | summary of the top incidents; improve the prompt based on the evaluation |
| **P4 · Adnan** | Vite skeleton, navigation, mock API; overview with mock data | timeline, event table, source view, chat page (mocks first, then real) | error groups, graph, ingest progress, quality & cost; polish the demo path |
| **P5 · open** | mentor questions; trace the demo scenario in the logs; 10–15 test questions with ground truth | `evaluate.py`; first run in the evening; report failures back to P2/P3 | final numbers, slides, demo script, backup video, README; leads the dress rehearsal |

### Syncs (short, max. 10 minutes)

- **Daily 9:00, 14:00, 19:00:** what is done, who blocks whom, does an interface change?
- **Day 1, 13:00:** interfaces are frozen.
- **Day 1, evening:** full ingest runs, fixture script is in the repo.
- **Day 2, evening:** the demo question works once end-to-end in the real frontend (integration milestone).
- **Day 3, 16:00:** feature freeze, then only bug fixes and the pitch.

### Rules against merge conflicts

- Everyone works only in **their own folders**, on **their own feature branches**, with small and frequent merges.
- **Shared files** such as `main.py` (registering routers), `pyproject.toml` and `package.json`: small changes only, tell the team before merging.
- Whoever changes an interface updates `contracts/examples/` in the same commit.

### Remaining dependencies (highest risk)

1. **P2 → P3:** the quality of the AI answer depends on good error groups and correlations. Real analysis tables for the demo scenario are needed by day 2 noon at the latest.
2. **P1 → everyone:** if a parser reads lines wrongly, everything downstream is wrong. Parser tests with real sample lines are mandatory.
3. **P3 → P5:** real evaluation numbers need the `/chat` endpoint. P5 can still have the test questions and ground truth ready before that.

## 12. Pitch structure (5 min)

1. **Problem** (45 s): Sandra, ticket "JT missing", 14 servers, 6 formats, 1.7 M lines, 3,345 ERRORs, and most of them are not the cause.
2. **Solution** (30 s): Log Tracer: all logs, one answer with evidence, uncertainty and verification steps.
3. **Live demo** (2 min): timeline → error group → chat question → causal chain across servers with evidence → click to the original line → a new log file is picked up live.
4. **How it works** (45 s): originals untouched · 6 parsers · dedupe (60 % copies) · clock correction · groups instead of ERRORs · LLM only via tools.
5. **Measured** (30 s): x of y test questions correct, 0 harmless ERRORs named as cause, z cents per question.
6. **Value for MAIT & outlook** (30 s): faster root-cause analysis in managed services, privacy via local LLM possible, knowledge base from solved tickets.

**Expected jury questions**: difference to Splunk/Elastic? (→ root-cause explanation with evidence instead of search, lightweight) · How reliable is the causality? (→ hypothesis with confidence, counter-evidence and verification steps; measured on test questions) · Cost? (→ context selection instead of everything into the LLM, numbers from `llm_calls`) · Scaling? (→ DuckDB → ClickHouse/Elastic, schema stays).

## 13. Open questions for the mentor (day 1)

- Where are `_dokumentation/FORMATE.md` and `INTEGRATION.md`? (time zones, limits, T4S/T4EA terminology)
- Which source has the skewed clock, and by how much? Should we find it ourselves or is it known?
- Is there a ground truth for `INC-01…10` and the `creative` scenarios?
- Are the `_runNN` copies intentional (dedupe test) or repeated runs?
- What role do `imported_mixed_hosts` and the `import_*` files play?
- Constraints on the LLM (cloud allowed? local preferred?) and the jury's judging criteria?

## 14. Risks & mitigations

| Risk | Mitigation |
|---|---|
| 13,643 files, ingest too slow | file-hash dedupe before parsing; DuckDB bulk insert; pre-build the DB before the pitch |
| Multi-line / incomplete entries break parsers | parser tests per format with real sample lines; "unparsed" fallback instead of crashing |
| Wrong ordering due to source clock | make the clock correction visible via `clock_offset_s` |
| LLM names harmless ERRORs as cause | error groups with retry status as tool output; a test question for it |
| LLM hallucinates | tool-based answers only, mandatory evidence, state uncertainty |
| Too much scope | feature freeze day 3, 16:00; could-stories only after MVP |
| Demo failure | backup video + locally pre-built DuckDB |
| Drain3 is unmaintained (last release 0.9.11, 2022) | install and test it on day 1 with our Python version; fallback: own regex masking + grouping by masked message |
| Time zones on Windows | Python's `zoneinfo` has no system time zone data on Windows: add the `tzdata` package as a backend dependency |

## 15. Definition of done (MVP)

- [ ] All 6 formats incl. gzip, Windows-1252 and multi-line exceptions are ingested; originals untouched
- [ ] Every event points to file + line; clicking shows the original with context
- [ ] File and event duplicates detected; incremental ingest via checkpoint
- [ ] Source clock skew detected and corrected
- [ ] Error groups with status "recovered" / "failed"
- [ ] Demo question returns a hypothesis across ≥ 3 servers with evidence, uncertainty and verification steps
- [ ] Harmless ERRORs are not named as cause
- [ ] Evaluation run with hit rate and cost per question
- [ ] Pitch + backup video done

## 16. TODO by phase

Role tags (see §11): **[ING]** P1 Safak, ingest & storage · **[ANA]** P2 Harsh, analysis & correlation · **[AI]** P3 Tarun, AI assistant · **[FE]** P4 Adnan, frontend · **[EVAL]** P5 *open*, data, evaluation & pitch (fallback split in §11) · **[ALL]** whole team.
Every phase ends with an **exit criterion**. A phase is only done once it is met.

### Phase 0: Setup (day 1, early)
- [ ] [ALL] Clone the repo, copy the log package locally to `MAIT_Makeathon_Logpaket/`
- [ ] [ING] Create `backend/`: `pyproject.toml` (uv), FastAPI skeleton, `/api/health`, `.env.example`
- [ ] [FE] Create `frontend/`: Vite + React 19 + TypeScript, Mantine, router, proxy `/api` → `:8000` (Node.js 22 or 24 LTS; Node 20 is end of life)
- [ ] [AI] Get a Claude API key, put it in `backend/.env` (never commit it)
- [ ] [EVAL] Read the log package README and `_dokumentation/`, prepare the mentor questions (§13)
- [ ] [ALL] Agree on branch rules (feature branch per person, short review before merge)

**Exit:** backend and frontend start locally, the frontend shows the response of `/api/health`.

### Phase 1: Concept, user stories & interfaces (day 1, morning)
- [ ] [ALL] Briefing, ask the mentor the questions (§13), request missing docs
- [ ] [ALL] Confirm personas and user stories, define the MVP cut
- [ ] [ALL] Assign the 5 roles (§11)
- [ ] [EVAL] Pick the demo scenario from §7 and trace it in the logs (files, lines, servers)
- [ ] [ING] Interface 1: `storage/schema.sql` incl. analysis tables; [ANA] confirms the analysis tables
- [ ] [ING] [ANA] [AI] Interface 2: one example JSON per own endpoint in `contracts/examples/`
- [ ] [AI] Interface 3: answer schema `answer.py` with an example answer
- [ ] [ALL] **Freeze the three interfaces by 13:00** (changes only by agreement)

**Exit:** prioritized backlog, chosen demo scenario, three frozen interfaces.

### Phase 2: Ingest & normalization (day 1, afternoon/evening)
- [ ] [ING] `scanner.py`: scan recursively, separate metadata (`server_info.json`, `README.md`), server/application/component from the path
- [ ] [ING] `fingerprint.py`: SHA-256 per file, only link byte-identical copies
- [ ] [ING] `reader.py`: `.gz` in memory, UTF-8 with Windows-1252 fallback, CRLF
- [ ] [ING] Parsers `kv_log`, `bracket_json`, `csv_semicolon` (multi-line), `jsonl`, `xml_events`, `freetext`
- [ ] [ING] Parser tests with real sample lines per format
- [ ] [ING] `db.py`: tables `sources`, `events`; Arrow batch insert
- [ ] [ING] `timestamps.py` (UTC), `levels.py` (level mapping), `dedupe.py` (event fingerprint, flag duplicates)
- [ ] [ING] `scripts/make_fixture.py`: small test DB from the demo scenario's files
- [ ] [ANA] Stand-in DB from the `.jsonl` files via `duckdb.read_json_auto()`, following the schema
- [ ] [ANA] Tune the Drain3 masking on real messages (order of the rules, `sim_th`)
- [ ] [AI] `providers/` (`ClaudeProvider`, interface for Ollama); first tools against the stand-in DB
- [ ] [EVAL] `eval/questions.yaml` v1: 10–15 test questions with expected cause, servers and evidence
- [ ] [FE] Page skeleton with navigation; mock API from `contracts/examples/`; overview with mock data

**Exit:** a full ingest runs through, all events are in DuckDB. Sanity check: events per server, level distribution and number of duplicates roughly match the analysis in §3. The fixture script is in the repo.

### Phase 3: Analysis (day 2, morning)
- [ ] [ANA] `templates.py`: Drain3 with masking, `template_id` per event
- [ ] [ANA] `error_groups.py`: build groups, status "recovered" / "failed"
- [ ] [ANA] `anomalies.py`: error rate vs. baseline, new/rare templates, duration outliers
- [ ] [ANA] `clock.py`: detect clock skew (`mait_win02_dispatcher_worker`), set `clock_offset_s`
- [ ] [ING] API: `/stats`, `/sources`, `/events`, `/events/{id}`, `/events/{id}/context`
- [ ] [AI] `tools.py`: `search_events`, `get_error_groups`, `get_anomalies`, `trace`, `correlate`, `get_context`
- [ ] [EVAL] `scripts/evaluate.py`: scoring against the ground truth, tested with the example answer from interface 3
- [ ] [FE] Timeline (ECharts) and event table, first against mocks, then against the real API
- [ ] [FE] `SourceViewer`: show the original lines around an event

**Exit:** error groups for the demo scenario are correct; harmless ERRORs end up as "recovered"; the timeline shows real data.

### Phase 4: Correlation & AI assistant (day 2, afternoon/evening)
- [ ] [ANA] `correlation.py`: hard (trace, job within a time window, object ID, `INC-xx`) and soft links; fill `incidents`
- [ ] [ANA] `graph.py` + API `/analysis/graph`, `/analysis/groups`, `/analysis/anomalies`, `/analysis/timeseries`, `/trace/{key}`
- [ ] [AI] `prompt.py` + evidence validation in `answer.py` (every cited event ID must exist)
- [ ] [AI] `agent.py`: tool-use loop with a round limit; `costs.py` writes `llm_calls`
- [ ] [AI] API `/chat` with SSE (`step`, `token`, `answer`, `done`)
- [ ] [FE] Chat page with intermediate steps, `AnswerCard`, `EvidenceChip` → `SourceViewer`
- [ ] [EVAL] First evaluation run against `/chat`; report wrong causes and missing evidence to [ANA] and [AI]

**Exit (milestone):** the demo question works once fully end-to-end in the frontend. First numbers on hit rate and cost are available.

### Phase 5: Continuous & completion (day 3, morning)
- [ ] [ING] `checkpoint.py`: byte offset/line per file, incremental ingest
- [ ] [ING] `watcher.py`: watchdog inside the backend process, ingest new files automatically
- [ ] [ING] API `/ingest` and `/ingest/progress` (SSE)
- [ ] [ANA] Flag late entries; make the clock correction visible in the timeline; incidents for the overview
- [ ] [AI] Optional: automatic summary of the top 3–5 incidents, stored in `hypotheses`
- [ ] [AI] Improve the prompt based on the evaluation
- [ ] [FE] Error groups page, dependency graph (Cytoscape.js), `IngestProgress`, overview with incidents
- [ ] [EVAL] Second evaluation run, track progress

**Exit:** a log file newly copied into the folder appears in the UI without a restart and without duplicates.

### Phase 6: Evaluation & polish (day 3, midday)
- [ ] [EVAL] Final evaluation run; compare "whole logs" vs. "tools" for cost; API `/eval/results`
- [ ] [FE] "Quality & cost" page with the numbers from `/eval/results`
- [ ] [ALL] Could-stories only once all must-stories are done (ticket draft, "happened before?", masking)
- [ ] [ALL] Bug fixing, click through the demo path several times
- [ ] [ALL] **Feature freeze 16:00**

**Exit:** every item of the definition of done (§15) is checked.

### Phase 7: Pitch preparation (day 3, afternoon/evening)
- [ ] [EVAL] Step-by-step demo script (which clicks, which question, which evidence)
- [ ] [EVAL] Slides following §12, with real numbers from the evaluation
- [ ] [EVAL] Repo README: project, how to run, architecture links
- [ ] [ALL] Record a backup video of the demo
- [ ] [ING] Pre-build and back up DuckDB; test startup without internet (except the LLM)
- [ ] [ALL] Timed dress rehearsal led by [EVAL], practice jury questions

**Exit:** the pitch fits in 5 minutes, the demo runs twice in a row without errors.

### Phase 8: Pitch day (day 4)
- [ ] [ALL] Final run-through in the morning
- [ ] [ING] Check the demo machine: backend, frontend, DuckDB, API key, internet
- [ ] [EVAL] Backup video and slides available offline
- [ ] [ALL] Deliver the pitch, answer questions
