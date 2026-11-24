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
