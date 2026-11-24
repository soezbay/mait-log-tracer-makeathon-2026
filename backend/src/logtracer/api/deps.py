"""Request dependencies: a DuckDB cursor per request and the configured log root.

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
    return request.app.state.settings.log_root
