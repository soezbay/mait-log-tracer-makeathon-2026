"""SQL for the `events` table."""

import json

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


LIST_COLUMNS = (
    "id", "ts_utc", "host", "component", "level", "event_id", "job_id", "trace_id", "message",
    "source_path", "line_start", "line_end", "is_duplicate", "is_late",
)

DETAIL_COLUMNS = (
    "id", "source_id", "source_path", "format", "encoding", "line_start", "line_end", "ts_raw",
    "ts_utc", "tz_assumed", "clock_offset_s", "host", "component", "level", "level_raw",
    "event_id", "job_id", "trace_id", "session_id", "message", "attrs", "template_id",
    "fingerprint", "duplicate_of", "is_late", "parse_error", "raw",
)

_SELECT_EXPR = {
    "source_path": "s.path",
    "format": "s.format",
    "encoding": "s.encoding",
    "is_duplicate": "e.duplicate_of IS NOT NULL",
    "attrs": "CAST(e.attrs AS VARCHAR)",
}


def _select(columns: tuple[str, ...]) -> str:
    return ", ".join(f"{_SELECT_EXPR.get(c, 'e.' + c)} AS {c}" for c in columns)


def _row_to_dict(columns: tuple[str, ...], row: tuple) -> dict:
    item = dict(zip(columns, row, strict=True))
    if "attrs" in item:
        item["attrs"] = json.loads(item["attrs"]) if item["attrs"] else {}
    return item


def search(
    con: duckdb.DuckDBPyConnection,
    *,
    host: str | None = None,
    component: str | None = None,
    levels: list[str] | None = None,
    ts_from=None,
    ts_to=None,
    q: str | None = None,
    job_id: str | None = None,
    trace_id: str | None = None,
    include_duplicates: bool = False,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[dict], int]:
    """Filtered, paginated event list sorted by time. Returns (items, total)."""
    where, params = [], []
    for column, value in (("host", host), ("component", component), ("job_id", job_id),
                          ("trace_id", trace_id)):
        if value:
            where.append(f"e.{column} = ?")
            params.append(value)
    if levels:
        where.append(f"e.level IN ({', '.join('?' * len(levels))})")
        params.extend(levels)
    if ts_from is not None:
        where.append("e.ts_utc >= ?")
        params.append(ts_from)
    if ts_to is not None:
        where.append("e.ts_utc <= ?")
        params.append(ts_to)
    if q:
        where.append("e.message ILIKE ?")
        params.append(f"%{q}%")
    if not include_duplicates:
        where.append("e.duplicate_of IS NULL")
    clause = f"WHERE {' AND '.join(where)}" if where else ""

    total = con.execute(f"SELECT count(*) FROM events e {clause}", params).fetchone()[0]
    rows = con.execute(
        f"SELECT {_select(LIST_COLUMNS)} FROM events e JOIN sources s USING (source_id) "
        f"{clause} ORDER BY e.ts_utc NULLS LAST, e.id LIMIT ? OFFSET ?",
        [*params, limit, offset],
    ).fetchall()
    return [_row_to_dict(LIST_COLUMNS, row) for row in rows], total


def get_event(con: duckdb.DuckDBPyConnection, event_pk: int) -> dict | None:
    row = con.execute(
        f"SELECT {_select(DETAIL_COLUMNS)} FROM events e JOIN sources s USING (source_id) "
        "WHERE e.id = ?",
        [event_pk],
    ).fetchone()
    return _row_to_dict(DETAIL_COLUMNS, row) if row else None


def next_id(con: duckdb.DuckDBPyConnection) -> int:
    return con.execute("SELECT coalesce(max(id), 0) + 1 FROM events").fetchone()[0]


def delete_for_source(con: duckdb.DuckDBPyConnection, source_id: int) -> None:
    con.execute("DELETE FROM events WHERE source_id = ?", [source_id])


def newest_ts_for_source(con: duckdb.DuckDBPyConnection, source_id: int):
    return con.execute(
        "SELECT max(ts_utc) FROM events WHERE source_id = ?", [source_id]
    ).fetchone()[0]


def most_common_assumed_date(con: duckdb.DuckDBPyConnection) -> str | None:
    """Date of most events without a source time zone (fallback for time-only lines)."""
    row = con.execute(
        "SELECT strftime(ts_utc, '%Y-%m-%d') FROM events WHERE tz_assumed "
        "GROUP BY 1 ORDER BY count(*) DESC LIMIT 1"
    ).fetchone()
    return row[0] if row else None


def mark_duplicates_since(con: duckdb.DuckDBPyConnection, first_new_id: int) -> int:
    """Flag duplicates among events with id >= first_new_id only (incremental ingest)."""
    con.execute(
        """
        UPDATE events SET duplicate_of = d.first_id
        FROM (
            SELECT fingerprint, min(id) AS first_id FROM events
            WHERE fingerprint IN (SELECT fingerprint FROM events WHERE id >= ?)
            GROUP BY fingerprint HAVING count(*) > 1
        ) d
        WHERE events.id >= ? AND events.fingerprint = d.fingerprint
          AND events.id <> d.first_id
        """,
        [first_new_id, first_new_id],
    )
    return con.execute(
        "SELECT count(*) FROM events WHERE id >= ? AND duplicate_of IS NOT NULL", [first_new_id]
    ).fetchone()[0]


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
