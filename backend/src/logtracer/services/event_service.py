"""Event and source queries for the API and the LLM tools (P3 calls the same functions)."""

from pathlib import Path

import duckdb

from logtracer.ingest.reader import read_text, split_lines
from logtracer.normalize.levels import LEVELS
from logtracer.storage.repositories import events as events_repo
from logtracer.storage.repositories import sources as sources_repo

MAX_CONTEXT_LINES = 50


def get_stats(con: duckdb.DuckDBPyConnection) -> dict:
    scan = sources_repo.scan_summary(con)
    events = events_repo.events_summary(con)
    return {
        "servers": scan["servers"],
        "sources": scan["sources"],
        "unique_sources": scan["unique_sources"],
        "duplicate_sources": scan["duplicate_sources"],
        "events": events["events"],
        "duplicate_events": events["duplicate_events"],
        "late_events": events["late_events"],
        "tz_assumed_events": events["tz_assumed_events"],
        "unparsed_events": events["unparsed_events"],
        "levels": {level: events["levels"].get(level, 0) for level in LEVELS},
        "time_range": events["time_range"],
        "last_ingest_at": sources_repo.last_ingest_at(con),
    }


def list_sources(con: duckdb.DuckDBPyConnection, **filters) -> tuple[list[dict], int]:
    return sources_repo.list_sources(con, **filters)


def search_events(con: duckdb.DuckDBPyConnection, **filters) -> tuple[list[dict], int]:
    return events_repo.search(con, **filters)


def get_event(con: duckdb.DuckDBPyConnection, event_pk: int) -> dict | None:
    return events_repo.get_event(con, event_pk)


def get_context(con: duckdb.DuckDBPyConnection, log_root: Path, event_pk: int,
                n: int = 10) -> dict | None:
    """The original lines around an event, read from the log file (also inside .gz)."""
    event = events_repo.get_event(con, event_pk)
    if event is None:
        return None
    n = max(0, min(n, MAX_CONTEXT_LINES))
    text, encoding = read_text(Path(log_root) / event["source_path"])
    lines = split_lines(text)
    start, end = event["line_start"], event["line_end"]
    first, last = max(1, start - n), min(len(lines), end + n)
    return {
        "id": event["id"],
        "source_path": event["source_path"],
        "format": event["format"],
        "encoding": encoding,
        "line_start": start,
        "line_end": end,
        "lines": [
            {"no": no, "is_event": start <= no <= end, "text": lines[no - 1]}
            for no in range(first, last + 1)
        ],
    }
