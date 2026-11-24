-- Log Tracer DuckDB schema (interface 1, see docs/plan.en.md §11).
-- Owner: P1 (Safak). Analysis tables: P2 (Harsh). Assistant tables: P3 (Tarun).
-- Changes only after a short team agreement; update contracts/examples/ in the same commit.
--
-- Conventions
--   * All timestamps are UTC, stored as TIMESTAMP (no time zone).
--   * Levels are normalized to DEBUG | INFO | WARN | ERROR | FATAL.
--   * No foreign keys and no primary key on `events`: DuckDB checks constraints eagerly,
--     which makes bulk inserts slower and can break UPDATEs (e.g. setting template_id).
--     Uniqueness of events.id is guaranteed by the ingest pipeline.
--   * Statements are idempotent (IF NOT EXISTS), so init_schema() can run on every start.

-- ---------------------------------------------------------------------------
-- P1 · Ingest & storage
-- ---------------------------------------------------------------------------

-- One row per server folder, from <server>/server_info.json.
CREATE TABLE IF NOT EXISTS servers (
    server      VARCHAR PRIMARY KEY,   -- folder name, e.g. mait_win03_cad_converter
    os          VARCHAR,               -- server_info.json: os_family (Linux | Windows)
    role        VARCHAR,               -- server_info.json: role, NULL for some servers
    info        JSON                   -- full server_info.json
);

CREATE SEQUENCE IF NOT EXISTS seq_source_id START 1;

-- One row per log file (README.md and server_info.json are not log files).
CREATE TABLE IF NOT EXISTS sources (
    source_id        INTEGER PRIMARY KEY DEFAULT nextval('seq_source_id'),
    path             VARCHAR NOT NULL UNIQUE, -- relative to LOG_ROOT, forward slashes
    server           VARCHAR NOT NULL,        -- first path segment
    application      VARCHAR,                 -- logs/<application>/...
    component        VARCHAR,                 -- rest of the folder path, e.g. converter/nx_jt or translators/nx_jt
    format           VARCHAR,                 -- kv_log | bracket_json | csv_semicolon | jsonl | xml_events | freetext
    encoding         VARCHAR,                 -- utf-8 | cp1252
    compressed       BOOLEAN NOT NULL DEFAULT FALSE,
    sha256           VARCHAR,                 -- over the decompressed bytes
    size             BIGINT,                  -- bytes on disk
    mtime            TIMESTAMP,
    duplicate_of     INTEGER,                 -- source_id of the first byte-identical file, then not parsed
    checkpoint_bytes BIGINT NOT NULL DEFAULT 0,
    checkpoint_line  BIGINT NOT NULL DEFAULT 0,
    event_count      BIGINT NOT NULL DEFAULT 0,
    ingested_at      TIMESTAMP
);

-- One row per (possibly multi-line) log entry.
CREATE TABLE IF NOT EXISTS events (
    id             BIGINT NOT NULL,       -- assigned by the pipeline, unique
    source_id      INTEGER NOT NULL,
    line_start     INTEGER NOT NULL,      -- 1-based, in the decompressed file
    line_end       INTEGER NOT NULL,
    ts_raw         VARCHAR,               -- timestamp text as found in the file
    ts_utc         TIMESTAMP,             -- UTC, after clock correction
    tz_assumed     BOOLEAN NOT NULL DEFAULT FALSE, -- source had no time zone, UTC assumed
    clock_offset_s DOUBLE NOT NULL DEFAULT 0,      -- applied correction in seconds (P2, clock.py)
    ingest_seq     BIGINT NOT NULL,       -- order of ingestion, to detect late entries
    host           VARCHAR,
    component      VARCHAR,
    level          VARCHAR,               -- DEBUG | INFO | WARN | ERROR | FATAL
    level_raw      VARCHAR,
    event_id       VARCHAR,               -- from the log, e.g. CREATIVE-00045771
    job_id         VARCHAR,
    trace_id       VARCHAR,
    session_id     VARCHAR,
    message        VARCHAR,
    attrs          JSON,                  -- all other fields: duration_ms, object, dependency, clock_offset_seconds, observed_at …
    template_id    INTEGER,               -- set by P2 (templates.py)
    fingerprint    VARCHAR,               -- sha1(host|event_id|ts_utc|message)
    duplicate_of   BIGINT,                -- id of the first event with the same fingerprint
    is_late        BOOLEAN NOT NULL DEFAULT FALSE,
    parse_error    VARCHAR,               -- NULL if parsed cleanly
    raw            VARCHAR NOT NULL       -- original text, all lines of the entry
);

-- ---------------------------------------------------------------------------
-- P2 · Analysis (Harsh). Proposal, to be confirmed at the 13:00 freeze.
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS templates (
    template_id INTEGER PRIMARY KEY,      -- Drain3 cluster id
    template    VARCHAR NOT NULL,         -- e.g. "Downstream timeout/retry during <INC>; dependency=<HOST>"
    count       BIGINT NOT NULL DEFAULT 0,
    first_seen  TIMESTAMP,
    last_seen   TIMESTAMP,
    in_baseline BOOLEAN                   -- also seen on the normal day (23 Nov)
);

CREATE TABLE IF NOT EXISTS error_groups (
    group_id         INTEGER PRIMARY KEY,
    template_id      INTEGER,
    host             VARCHAR,
    component        VARCHAR,
    level            VARCHAR,             -- highest level in the group
    count            BIGINT NOT NULL,
    first_ts         TIMESTAMP,
    last_ts          TIMESTAMP,
    status           VARCHAR,             -- recovered | failed | unknown
    sample_event_ids BIGINT[]
);

CREATE TABLE IF NOT EXISTS group_members (
    group_id INTEGER NOT NULL,
    event_pk BIGINT NOT NULL              -- events.id
);

CREATE TABLE IF NOT EXISTS anomalies (
    anomaly_id   INTEGER PRIMARY KEY,
    host         VARCHAR,
    component    VARCHAR,
    kind         VARCHAR,                 -- rate_spike | new_template | level_jump | duration_outlier
    window_start TIMESTAMP,
    window_end   TIMESTAMP,
    score        DOUBLE,
    details      JSON
);

CREATE TABLE IF NOT EXISTS correlations (
    correlation_id INTEGER PRIMARY KEY,
    group_a        INTEGER NOT NULL,      -- earlier group (candidate cause)
    group_b        INTEGER NOT NULL,      -- later group (candidate effect)
    kind           VARCHAR,               -- hard | soft
    link_key       VARCHAR,               -- e.g. job_id=JOB-2003, trace_id=…, dependency=…
    lag_s          DOUBLE,
    confidence     DOUBLE
);

CREATE TABLE IF NOT EXISTS incidents (
    incident_id   INTEGER PRIMARY KEY,
    title         VARCHAR,
    first_ts      TIMESTAMP,
    last_ts       TIMESTAMP,
    status        VARCHAR,                -- recovered | failed | unknown
    hosts         VARCHAR[],
    group_ids     INTEGER[],
    root_group_id INTEGER,                -- most likely cause
    confidence    DOUBLE
);

-- ---------------------------------------------------------------------------
-- P3 · AI assistant (Tarun). Proposal, to be confirmed at the 13:00 freeze.
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS hypotheses (
    hypothesis_id   INTEGER PRIMARY KEY,
    incident_id     INTEGER,
    conversation_id VARCHAR,
    question        VARCHAR,
    answer          JSON,                 -- answer schema from assistant/answer.py
    model           VARCHAR,
    created_at      TIMESTAMP
);

CREATE TABLE IF NOT EXISTS llm_calls (
    call_id         INTEGER PRIMARY KEY,
    conversation_id VARCHAR,
    hypothesis_id   INTEGER,
    model           VARCHAR,
    input_tokens    INTEGER,
    output_tokens   INTEGER,
    duration_ms     INTEGER,
    cost_eur        DOUBLE,
    created_at      TIMESTAMP
);

CREATE TABLE IF NOT EXISTS chat_messages (
    message_id      INTEGER PRIMARY KEY,
    conversation_id VARCHAR NOT NULL,
    role            VARCHAR NOT NULL,     -- user | assistant | tool
    content         VARCHAR,
    answer          JSON,                 -- structured answer for assistant messages
    created_at      TIMESTAMP
);
