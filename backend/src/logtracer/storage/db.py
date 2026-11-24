"""DuckDB connection and schema setup.

Only one process may open the database file for writing, so the backend keeps a single
connection and hands out cursors for concurrent reads.
"""

from pathlib import Path

import duckdb

SCHEMA_FILE = Path(__file__).with_name("schema.sql")


def connect(db_path: Path | str) -> duckdb.DuckDBPyConnection:
    """Open (or create) the database file. Use ':memory:' for tests."""
    if str(db_path) != ":memory:":
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    return duckdb.connect(str(db_path))


def init_schema(con: duckdb.DuckDBPyConnection) -> None:
    """Create all tables. Safe to run on every start (IF NOT EXISTS)."""
    con.execute(SCHEMA_FILE.read_text(encoding="utf-8"))
