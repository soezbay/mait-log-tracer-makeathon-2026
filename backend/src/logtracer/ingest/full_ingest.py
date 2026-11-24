"""Full ingest: scan -> parse -> normalize -> write events -> flag duplicates.

Rebuilds `servers`, `sources` and `events` from the log package. The log files are only read.
Only one process may write the DuckDB file: run it from the API (POST /api/ingest) or, with
the API stopped, from scripts/ingest.py.
"""

import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import duckdb

from logtracer.ingest.event_writer import EventWriter
from logtracer.ingest.parse_run import iter_parsed_sources
from logtracer.ingest.pipeline import ScanResult, scan_sources
from logtracer.storage.repositories import events as events_repo
from logtracer.storage.repositories import sources as sources_repo

Progress = Callable[[int, int, int], None]  # files_done, files_total, events_written


@dataclass
class IngestResult:
    scan: ScanResult
    files: int
    events: int
    duplicate_events: int
    elapsed_s: float


def full_ingest(
    con: duckdb.DuckDBPyConnection,
    log_root: Path,
    batch_size: int = 50_000,
    default_tz: str = "UTC",
    progress: Progress | None = None,
    progress_every: int = 500,
) -> IngestResult:
    started = time.perf_counter()
    scan = scan_sources(con, log_root)
    files_total = con.execute(
        "SELECT count(*) FROM sources WHERE duplicate_of IS NULL"
    ).fetchone()[0]
    events_repo.clear(con)

    writer = EventWriter(con, next_id=1, batch_size=batch_size, default_tz=default_tz)
    formats: dict[int, str] = {}
    results: dict[int, tuple[int, int]] = {}

    for files_done, parsed in enumerate(iter_parsed_sources(con, log_root), start=1):
        formats[parsed.source_id] = parsed.format
        results[parsed.source_id] = writer.add_file(parsed.source_id, parsed.events)
        if progress and files_done % progress_every == 0:
            progress(files_done, files_total, writer.written + writer.pending)

    writer.flush()
    sources_repo.set_formats(con, formats)
    sources_repo.set_ingest_results(con, results)
    duplicates = events_repo.mark_duplicates(con)
    if progress:
        progress(files_total, files_total, writer.written)
    return IngestResult(
        scan=scan,
        files=len(results),
        events=writer.written,
        duplicate_events=duplicates,
        elapsed_s=round(time.perf_counter() - started, 2),
    )
