# Makeathon Plan: AI Log Assistant for MAIT

> Working title: **LogLens** · Challenge: *Automated log file management with an AI assistant* (MAIT)
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
- **2026-11-23**: normal operation (`NORMAL-…` jobs), baseline.
- **2026-11-24** (`creative_*`): targeted error scenarios in all formats.

**Correlation keys**: `job_id`, `trace_id`, `session_id`, `event_id`, `INC-xx`, `dependency=<host>`, object IDs (`DEMO-…`, `DEMO-Seal-17/C`), request IDs (`REQ-…`).

**Error patterns found (candidates for demo & evaluation)**
- Downstream timeouts with a dependency on the Teamcenter DB or the dispatcher master (`INC-01…10`)
- "Worker failed … **local clock is behind**" → skewed source clock (`mait_win02_dispatcher_worker`)
- **Converter reports SUCCESS, publish finds no result** → contradicting systems
- **Missing assembly reference** `DEMO-Seal-17/C` → "No output JT produced" (multi-line Java exception)
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

1. **"JT missing although the converter reports SUCCESS"** (24 Nov): converter `SUCCESS` → publish "no registered result" → cause: missing reference `DEMO-Seal-17/C` (multi-line exception). Shows **contradicting systems + multi-line**.
2. **`INC-01` in October**: the Teamcenter app repeatedly reports downstream timeouts to `teamcenter_db`. Many ERRORs, **one cause**, partly successful retries. Shows **grouping + retry ≠ failure**.
3. **"Worker failed, local clock is behind"** (`mait_win02_dispatcher_worker`): shows **source clock correction**. Without it, the order of the chain is wrong.

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
                           │ loglens.duckdb│               │ LLM + tool use   │
                           └──────────────┘               └────────┬─────────┘
                                                                   ▼
                     UI: timeline · error groups · dependency graph · chat with evidence
```

### Principle: originals stay untouched

Log files are **read only**. Everything derived lives in **one DuckDB file** (`data/loglens.duckdb`) that a script can rebuild at any time. Every event points back to its original file and line.

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
| Backend / API | FastAPI + Uvicorn, Pydantic, SSE | clear interface, OpenAPI docs, live streaming |
| Frontend | React + TypeScript (Vite), Mantine, ECharts, Cytoscape.js; fallback Streamlit | separated from the backend, only via the API |

Details on all frameworks and components: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## 9. Repo structure (target)

```
makeathon/
├── plan.md / plan.en.md
├── docs/ARCHITEKTUR.md · ARCHITECTURE.md
├── MAIT_Makeathon_Logpaket/   # original data, read only, in .gitignore
├── data/loglens.duckdb        # derived, in .gitignore
├── eval/questions.yaml        # test questions + ground truth
├── backend/                   # Python + FastAPI
│   └── src/loglens/
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
| Midday | Lock data model + parser list, assign roles | schema, tasks |
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

## 11. Roles (assumption: 4 people)

| Role | Responsibility |
|---|---|
| **Ingest** | scanner, parsers, encoding, DuckDB, checkpoints, dedupe |
| **Analytics** | templates, error groups, anomalies, clock correction, correlation |
| **AI & evaluation** | LLM tools, prompt, answer format, test questions, quality & cost |
| **Frontend & pitch** | React frontend, graph, demo script, slides, story |

## 12. Pitch structure (5 min)

1. **Problem** (45 s): Sandra, ticket "JT missing", 14 servers, 6 formats, 1.7 M lines, 3,345 ERRORs, and most of them are not the cause.
2. **Solution** (30 s): LogLens: all logs, one answer with evidence, uncertainty and verification steps.
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
