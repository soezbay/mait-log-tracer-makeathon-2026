"""Request dependencies: a DuckDB cursor per request and the active log root.

The app keeps one DuckDB connection (only one process may write the file); each request gets
its own cursor, which is safe to use from FastAPI's worker threads.
"""

from collections.abc import Iterator
from pathlib import Path

import duckdb
from fastapi import Request


def get_cursor(request: Request) -> Iterator[duckdb.DuckDBPyConnection]:
    cursor = request.app.state.db.cursor()
    try:
        yield cursor
    finally:
        cursor.close()


def get_log_root(request: Request) -> Path:
    """The log folder of the active data set (original package or an uploaded ZIP)."""
    ingest = getattr(request.app.state, "ingest", None)
    return ingest.log_root if ingest is not None else request.app.state.settings.log_root
