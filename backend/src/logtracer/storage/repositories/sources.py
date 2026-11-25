"""SQL for the `servers` and `sources` tables."""

import json
from dataclasses import dataclass

import duckdb
import pyarrow as pa

from logtracer.ingest.scanner import ServerInfo


@dataclass
class SourceRow:
    source_id: int
    path: str
    server: str
    application: str | None
    component: str | None
    format: str | None
    encoding: str | None
    compressed: bool
    sha256: str | None
    size: int
    mtime: object  # datetime
    duplicate_of: int | None
    ingested_at: object  # datetime


def replace_servers(con: duckdb.DuckDBPyConnection, servers: list[ServerInfo]) -> None:
    table = pa.table({
        "server": [s.server for s in servers],
        "os": [s.os for s in servers],
        "role": [s.role for s in servers],
        "info": [json.dumps(s.info) for s in servers],
    })
    con.execute("DELETE FROM servers")
    con.register("_servers_batch", table)
    try:
        con.execute(
            "INSERT INTO servers (server, os, role, info) "
            "SELECT server, os, role, info::JSON FROM _servers_batch"
        )
    finally:
        con.unregister("_servers_batch")


def replace_sources(con: duckdb.DuckDBPyConnection, rows: list[SourceRow]) -> None:
    """Replace all sources in one batch (full scan)."""
    columns = list(SourceRow.__dataclass_fields__)
    table = pa.table({col: [getattr(r, col) for r in rows] for col in columns})
    con.execute("DELETE FROM sources")
    con.register("_sources_batch", table)
    try:
        con.execute(
            f"INSERT INTO sources ({', '.join(columns)}) "
            f"SELECT {', '.join(columns)} FROM _sources_batch"
        )
    finally:
        con.unregister("_sources_batch")


def set_formats(con: duckdb.DuckDBPyConnection, formats: dict[int, str]) -> None:
    """Store the detected format per unique source; duplicates inherit it from their original."""
    table = pa.table({
        "source_id": pa.array(list(formats), pa.int32()),
        "format": list(formats.values()),
    })
    con.register("_formats_batch", table)
    try:
        con.execute(
            "UPDATE sources SET format = f.format FROM _formats_batch f "
            "WHERE sources.source_id = f.source_id"
        )
        con.execute(
            "UPDATE sources SET format = o.format FROM sources o "
            "WHERE sources.duplicate_of = o.source_id"
        )
    finally:
        con.unregister("_formats_batch")


def set_ingest_results(con: duckdb.DuckDBPyConnection,
                       results: dict[int, tuple[int, int]]) -> None:
    """Store per unique source: event_count and checkpoint (last line read; bytes for plain files).

    `results` maps source_id -> (event_count, last_line). Duplicates keep event_count 0.
    """
    table = pa.table({
        "source_id": pa.array(list(results), pa.int32()),
        "event_count": pa.array([r[0] for r in results.values()], pa.int64()),
        "last_line": pa.array([r[1] for r in results.values()], pa.int64()),
    })
    con.register("_ingest_results", table)
    try:
        con.execute(
            "UPDATE sources SET event_count = r.event_count, checkpoint_line = r.last_line, "
            "checkpoint_bytes = CASE WHEN sources.compressed THEN 0 ELSE sources.size END "
            "FROM _ingest_results r WHERE sources.source_id = r.source_id"
        )
    finally:
        con.unregister("_ingest_results")


def scan_summary(con: duckdb.DuckDBPyConnection) -> dict:
    """Counts used by the ingest report and later by GET /api/stats."""
    total, unique, dupes, size_all, size_unique = con.execute(
        "SELECT count(*), count(*) FILTER (WHERE duplicate_of IS NULL), "
        "count(*) FILTER (WHERE duplicate_of IS NOT NULL), "
        "coalesce(sum(size), 0), coalesce(sum(size) FILTER (WHERE duplicate_of IS NULL), 0) "
        "FROM sources"
    ).fetchone()
    per_server = con.execute(
        "SELECT s.server, v.os, count(*), count(*) FILTER (WHERE duplicate_of IS NULL) "
        "FROM sources s LEFT JOIN servers v USING (server) GROUP BY ALL ORDER BY s.server"
    ).fetchall()
    encodings = dict(con.execute(
        "SELECT coalesce(encoding, 'unreadable'), count(*) FROM sources "
        "WHERE duplicate_of IS NULL GROUP BY ALL ORDER BY 2 DESC"
    ).fetchall())
    return {
        "servers": con.execute("SELECT count(*) FROM servers").fetchone()[0],
        "sources": total,
        "unique_sources": unique,
        "duplicate_sources": dupes,
        "bytes_on_disk": size_all,
        "bytes_unique_on_disk": size_unique,
        "encodings_unique": encodings,
        "per_server": [
            {"server": s, "os": o, "files": n, "unique": u} for s, o, n, u in per_server
        ],
    }


SOURCE_COLUMNS = (
    "original_path", "copies",
    "source_id", "path", "server", "os", "application", "component", "format", "encoding",
    "compressed", "size", "sha256", "duplicate_of", "event_count", "checkpoint_bytes",
    "checkpoint_line", "ingested_at",
)


def list_sources(
    con: duckdb.DuckDBPyConnection,
    *,
    server: str | None = None,
    fmt: str | None = None,
    duplicates: bool | None = None,
    q: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[dict], int]:
    """Sources with server OS, filtered and paginated. Returns (items, total).

    Copies are not parsed, so they take the format of their original.
    """
    where, params = [], []
    if server:
        where.append("s.server = ?")
        params.append(server)
    if fmt:
        where.append("coalesce(s.format, o.format) = ?")
        params.append(fmt)
    if q:
        where.append("s.path ILIKE ?")
        params.append(f"%{q.strip()}%")
    if duplicates is not None:
        where.append("s.duplicate_of IS NOT NULL" if duplicates else "s.duplicate_of IS NULL")
    clause = f"WHERE {' AND '.join(where)}" if where else ""
    joins = "LEFT JOIN sources o ON o.source_id = s.duplicate_of"
    total = con.execute(
        f"SELECT count(*) FROM sources s {joins} {clause}", params).fetchone()[0]
    special = {"os": "v.os", "format": "coalesce(s.format, o.format)", "original_path": "o.path",
               "copies": "(SELECT count(*) FROM sources c WHERE c.duplicate_of = s.source_id)"}
    select = ", ".join(special.get(c, f"s.{c}") for c in SOURCE_COLUMNS)
    rows = con.execute(
        f"SELECT {select} FROM sources s LEFT JOIN servers v ON v.server = s.server {joins} "
        f"{clause} ORDER BY s.source_id LIMIT ? OFFSET ?",
        [*params, limit, offset],
    ).fetchall()
    return [dict(zip(SOURCE_COLUMNS, row, strict=True)) for row in rows], total


def overview(con: duckdb.DuckDBPyConnection) -> dict:
    """Files, copies, events and real errors per server and per format."""

    def rows(sql: str) -> list[dict]:
        result = con.execute(sql)
        columns = [c[0] for c in result.description]
        return [dict(zip(columns, row, strict=True)) for row in result.fetchall()]

    servers = rows(
        """
        WITH files AS (
            SELECT server, count(*) AS files, count(duplicate_of) AS copies,
                   coalesce(sum(event_count), 0)::BIGINT AS events,
                   coalesce(sum(size), 0)::BIGINT AS bytes,
                   list(DISTINCT format ORDER BY format) FILTER (WHERE format IS NOT NULL)
                       AS formats
            FROM sources GROUP BY server
        ), seen AS (
            SELECT s.server, count(e.duplicate_of) AS duplicate_events,
                   count(e.parse_error) AS unparsed_events, min(e.ts_utc) AS first_ts,
                   max(e.ts_utc) AS last_ts
            FROM events e JOIN sources s USING (source_id) GROUP BY s.server
        ), errors AS (  -- only real problems are members of an error group
            SELECT s.server, count(*) AS errors
            FROM group_members m JOIN events e ON e.id = m.event_pk
            JOIN sources s USING (source_id)
            WHERE e.level IN ('ERROR', 'FATAL') GROUP BY s.server
        )
        SELECT v.server, v.os, v.role, coalesce(f.files, 0) AS files,
               coalesce(f.copies, 0) AS copies, coalesce(f.events, 0) AS events,
               coalesce(f.bytes, 0) AS bytes, coalesce(f.formats, []) AS formats,
               coalesce(x.duplicate_events, 0) AS duplicate_events,
               coalesce(x.unparsed_events, 0) AS unparsed_events, x.first_ts, x.last_ts,
               coalesce(r.errors, 0) AS errors
        FROM servers v LEFT JOIN files f USING (server) LEFT JOIN seen x USING (server)
        LEFT JOIN errors r USING (server) ORDER BY v.server
        """
    )
    formats = rows(
        """
        SELECT coalesce(s.format, o.format, 'unknown') AS format, count(*) AS files,
               count(s.duplicate_of) AS copies, coalesce(sum(s.event_count), 0)::BIGINT AS events
        FROM sources s LEFT JOIN sources o ON o.source_id = s.duplicate_of
        GROUP BY 1 ORDER BY events DESC, format
        """
    )
    return {"servers": servers, "formats": formats}


def upsert_server(con: duckdb.DuckDBPyConnection, server: ServerInfo) -> None:
    con.execute(
        "INSERT INTO servers (server, os, role, info) VALUES (?, ?, ?, ?::JSON) "
        "ON CONFLICT (server) DO UPDATE SET os = excluded.os, role = excluded.role, "
        "info = excluded.info",
        [server.server, server.os, server.role, json.dumps(server.info)],
    )


def source_index(con: duckdb.DuckDBPyConnection) -> dict[str, dict]:
    """path -> current source row (for the incremental ingest)."""
    cols = ("source_id", "path", "size", "mtime", "sha256", "duplicate_of", "event_count",
            "checkpoint_line", "compressed")
    rows = con.execute(f"SELECT {', '.join(cols)} FROM sources").fetchall()
    return {row[1]: dict(zip(cols, row, strict=True)) for row in rows}


def original_for_hash(con: duckdb.DuckDBPyConnection, digest: str,
                      exclude_id: int | None = None) -> int | None:
    row = con.execute(
        "SELECT min(source_id) FROM sources WHERE sha256 = ? AND duplicate_of IS NULL "
        "AND source_id IS DISTINCT FROM ?",
        [digest, exclude_id],
    ).fetchone()
    return row[0]


def next_source_id(con: duckdb.DuckDBPyConnection) -> int:
    return con.execute("SELECT coalesce(max(source_id), 0) + 1 FROM sources").fetchone()[0]


def save_source(con: duckdb.DuckDBPyConnection, row: dict) -> None:
    """Insert or replace one source row (all columns of the table)."""
    cols = list(row)
    updates = ", ".join(f"{c} = excluded.{c}" for c in cols if c not in ("source_id", "path"))
    con.execute(
        f"INSERT INTO sources ({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))}) "
        f"ON CONFLICT (source_id) DO UPDATE SET {updates}",
        [row[c] for c in cols],
    )


def last_ingest_at(con: duckdb.DuckDBPyConnection):
    return con.execute("SELECT max(ingested_at) FROM sources").fetchone()[0]
