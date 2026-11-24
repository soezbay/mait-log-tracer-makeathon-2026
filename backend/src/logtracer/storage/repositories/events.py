"""SQL for the `events` table."""

import duckdb
import pyarrow as pa

# Column order of the batches written by the ingest; matches storage/schema.sql.
EVENT_COLUMNS = (
    "id", "source_id", "line_start", "line_end", "ts_raw", "ts_utc", "tz_assumed",
    "clock_offset_s", "ingest_seq", "host", "component", "level", "level_raw", "event_id",
    "job_id", "trace_id", "session_id", "message", "attrs", "template_id", "fingerprint",
    "duplicate_of", "is_late", "parse_error", "raw",
)

_SCHEMA = pa.schema([
    ("id", pa.int64()), ("source_id", pa.int32()), ("line_start", pa.int32()),
    ("line_end", pa.int32()), ("ts_raw", pa.string()), ("ts_utc", pa.timestamp("us")),
    ("tz_assumed", pa.bool_()), ("clock_offset_s", pa.float64()), ("ingest_seq", pa.int64()),
    ("host", pa.string()), ("component", pa.string()), ("level", pa.string()),
    ("level_raw", pa.string()), ("event_id", pa.string()), ("job_id", pa.string()),
    ("trace_id", pa.string()), ("session_id", pa.string()), ("message", pa.string()),
    ("attrs", pa.string()), ("template_id", pa.int32()), ("fingerprint", pa.string()),
    ("duplicate_of", pa.int64()), ("is_late", pa.bool_()), ("parse_error", pa.string()),
    ("raw", pa.string()),
])


def new_batch() -> dict[str, list]:
    return {col: [] for col in EVENT_COLUMNS}


def clear(con: duckdb.DuckDBPyConnection) -> None:
    con.execute("DELETE FROM events")


def insert_batch(con: duckdb.DuckDBPyConnection, batch: dict[str, list]) -> int:
    """Insert one batch (column lists) in a single statement. Returns the number of rows."""
    rows = len(batch["id"])
    if rows == 0:
        return 0
    table = pa.Table.from_pydict(batch, schema=_SCHEMA)
    con.register("_events_batch", table)
    try:
        columns = ", ".join(EVENT_COLUMNS)
        select = ", ".join("attrs::JSON" if c == "attrs" else c for c in EVENT_COLUMNS)
        con.execute(f"INSERT INTO events ({columns}) SELECT {select} FROM _events_batch")
    finally:
        con.unregister("_events_batch")
    return rows


def mark_duplicates(con: duckdb.DuckDBPyConnection) -> int:
    """Set duplicate_of to the first id with the same fingerprint. Returns the number marked."""
    con.execute("UPDATE events SET duplicate_of = NULL WHERE duplicate_of IS NOT NULL")
    con.execute(
        """
        UPDATE events SET duplicate_of = d.first_id
        FROM (
            SELECT fingerprint, min(id) AS first_id
            FROM events GROUP BY fingerprint HAVING count(*) > 1
        ) d
        WHERE events.fingerprint = d.fingerprint AND events.id <> d.first_id
        """
    )
    return con.execute("SELECT count(*) FROM events WHERE duplicate_of IS NOT NULL").fetchone()[0]


def events_summary(con: duckdb.DuckDBPyConnection) -> dict:
    """Counts for the ingest report and GET /api/stats."""
    total, dupes, late, tz_assumed, errors, no_ts, ts_min, ts_max = con.execute(
        "SELECT count(*), count(duplicate_of), count(*) FILTER (WHERE is_late), "
        "count(*) FILTER (WHERE tz_assumed), count(parse_error), "
        "count(*) FILTER (WHERE ts_utc IS NULL), min(ts_utc), max(ts_utc) FROM events"
    ).fetchone()
    levels = dict(con.execute(
        "SELECT coalesce(level, 'UNKNOWN'), count(*) FROM events GROUP BY ALL ORDER BY 2 DESC"
    ).fetchall())
    per_day = dict(con.execute(
        "SELECT strftime(ts_utc, '%Y-%m-%d') AS day, count(*) FROM events "
        "WHERE ts_utc IS NOT NULL GROUP BY ALL ORDER BY day"
    ).fetchall())
    return {
        "events": total,
        "duplicate_events": dupes,
        "late_events": late,
        "tz_assumed_events": tz_assumed,
        "unparsed_events": errors,
        "events_without_timestamp": no_ts,
        "levels": levels,
        "time_range": {"from": ts_min, "to": ts_max},
        "events_per_day": per_day,
    }
