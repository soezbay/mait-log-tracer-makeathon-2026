"""Full ingest: scan -> parse -> normalize -> write events -> flag duplicates.

Rebuilds `servers`, `sources` and `events` from the log package. The log files are only read.
Only one process may write the DuckDB file, so run this while the API server is stopped.
"""

import json
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import duckdb

from logtracer.ingest.parse_run import iter_parsed_sources
from logtracer.ingest.pipeline import ScanResult, scan_sources
from logtracer.normalize.dedupe import LateDetector, fingerprint
from logtracer.normalize.levels import normalize_level
from logtracer.normalize.timestamps import to_utc
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

    batch = events_repo.new_batch()
    next_id = 1
    written = 0
    formats: dict[int, str] = {}
    results: dict[int, tuple[int, int]] = {}

    for files_done, parsed in enumerate(iter_parsed_sources(con, log_root), start=1):
        formats[parsed.source_id] = parsed.format
        late = LateDetector()
        last_line = 0
        for ev in parsed.events:
            ts_utc, tz_assumed = to_utc(ev.ts, default_tz)
            batch["id"].append(next_id)
            batch["source_id"].append(parsed.source_id)
            batch["line_start"].append(ev.line_start)
            batch["line_end"].append(ev.line_end)
            batch["ts_raw"].append(ev.ts_raw)
            batch["ts_utc"].append(ts_utc)
            batch["tz_assumed"].append(tz_assumed)
            batch["clock_offset_s"].append(0.0)
            batch["ingest_seq"].append(next_id)
            batch["host"].append(ev.host)
            batch["component"].append(ev.component)
            batch["level"].append(normalize_level(ev.level_raw))
            batch["level_raw"].append(ev.level_raw)
            batch["event_id"].append(ev.event_id)
            batch["job_id"].append(ev.job_id)
            batch["trace_id"].append(ev.trace_id)
            batch["session_id"].append(ev.session_id)
            batch["message"].append(ev.message)
            batch["attrs"].append(json.dumps(ev.attrs) if ev.attrs else None)
            batch["template_id"].append(None)
            batch["fingerprint"].append(fingerprint(ev.host, ev.event_id, ts_utc, ev.message))
            batch["duplicate_of"].append(None)
            batch["is_late"].append(late.is_late(ts_utc))
            batch["parse_error"].append(ev.parse_error)
            batch["raw"].append(ev.raw)
            next_id += 1
            last_line = max(last_line, ev.line_end)
            if len(batch["id"]) >= batch_size:
                written += events_repo.insert_batch(con, batch)
                batch = events_repo.new_batch()
        results[parsed.source_id] = (len(parsed.events), last_line)
        if progress and files_done % progress_every == 0:
            progress(files_done, files_total, written + len(batch["id"]))

    written += events_repo.insert_batch(con, batch)
    sources_repo.set_formats(con, formats)
    sources_repo.set_ingest_results(con, results)
    duplicates = events_repo.mark_duplicates(con)
    if progress:
        progress(files_total, files_total, written)
    return IngestResult(
        scan=scan,
        files=len(results),
        events=written,
        duplicate_events=duplicates,
        elapsed_s=round(time.perf_counter() - started, 2),
    )
