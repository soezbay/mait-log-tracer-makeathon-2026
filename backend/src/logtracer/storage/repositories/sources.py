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
