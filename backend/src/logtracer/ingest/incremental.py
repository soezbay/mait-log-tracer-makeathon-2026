"""Incremental ingest with checkpoints (MAIT step 3: process new entries continuously).

For every candidate file the stored checkpoint decides what to do:
- unknown file              -> new source, all entries are ingested
- size and mtime unchanged  -> skipped
- same content hash         -> only size/mtime updated
- byte-identical to another original -> recorded as duplicate, not parsed
- grown                     -> only entries after `checkpoint_line` are added
- shrunk, or was a copy     -> its events are replaced (file was rewritten)

The whole file is parsed each time (needed for CSV headers and multi-line entries); only the
new entries are written. Event duplicates are flagged for the new ids only. Deleted files are
ignored: their events stay, because the log package is the record of what happened.
"""

import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

import duckdb

from logtracer.ingest.detector import detect_format
from logtracer.ingest.event_writer import EventWriter
from logtracer.ingest.fingerprint import sha256
from logtracer.ingest.models import ParseContext
from logtracer.ingest.parse_run import infer_default_date
from logtracer.ingest.parsers import parse
from logtracer.ingest.reader import decode, read_bytes
from logtracer.ingest.scanner import ScannedFile, read_server_info, scan, scan_file
from logtracer.storage.repositories import events as events_repo
from logtracer.storage.repositories import sources as sources_repo

FileCallback = Callable[[str, str, int], None]  # path, action, new events


@dataclass
class IncrementalResult:
    files_checked: int = 0
    files_new: int = 0
    files_appended: int = 0
    files_rewritten: int = 0
    files_duplicate: int = 0
    files_unchanged: int = 0
    events_written: int = 0
    duplicate_events: int = 0
    elapsed_s: float = 0.0
    changes: list[dict] = field(default_factory=list)  # {"path", "action", "events"}


def _candidates(log_root: Path, paths: Iterable[Path] | None) -> list[ScannedFile]:
    if paths is None:
        return scan(log_root)[1]
    found = (scan_file(log_root, p) for p in paths)
    return sorted((f for f in found if f is not None), key=lambda f: f.path)


def incremental_ingest(
    con: duckdb.DuckDBPyConnection,
    log_root: Path,
    paths: Iterable[Path] | None = None,
    batch_size: int = 50_000,
    default_tz: str = "UTC",
    on_file: FileCallback | None = None,
) -> IncrementalResult:
    """Ingest new or changed files. `paths=None` checks the whole log package."""
    started = time.perf_counter()
    log_root = Path(log_root)
    result = IncrementalResult()
    index = sources_repo.source_index(con)
    known_servers = {r[0] for r in con.execute("SELECT server FROM servers").fetchall()}
    first_new_id = events_repo.next_id(con)
    writer = EventWriter(con, next_id=first_new_id, batch_size=batch_size, default_tz=default_tz)
    fallback_date = events_repo.most_common_assumed_date(con)
    now = datetime.now(UTC).replace(tzinfo=None)

    for f in _candidates(log_root, paths):
        result.files_checked += 1
        row = index.get(f.path)
        # Full scans skip by size/mtime. Files reported by the watcher are always compared by
        # content hash: on Windows the change notification can arrive while size and mtime
        # still show the old values, and the change would otherwise be missed.
        if paths is None and row and row["size"] == f.size and row["mtime"] == f.mtime:
            result.files_unchanged += 1
            continue
        if f.server not in known_servers:
            sources_repo.upsert_server(con, read_server_info(log_root / f.server))
            known_servers.add(f.server)

        data = read_bytes(f.abs_path)
        digest = sha256(data)
        source_id = row["source_id"] if row else sources_repo.next_source_id(con)
        base = {
            "source_id": source_id, "path": f.path, "server": f.server,
            "application": f.application, "component": f.component,
            "compressed": f.compressed, "sha256": digest, "size": f.size, "mtime": f.mtime,
            "ingested_at": now,
        }

        if row and row["sha256"] == digest:  # touched, same content
            con.execute("UPDATE sources SET size = ?, mtime = ? WHERE source_id = ?",
                        [f.size, f.mtime, source_id])
            result.files_unchanged += 1
            continue

        original = sources_repo.original_for_hash(con, digest, exclude_id=source_id)
        if original is not None:  # byte-identical copy of another file
            if row:
                events_repo.delete_for_source(con, source_id)
            fmt, enc = con.execute("SELECT format, encoding FROM sources WHERE source_id = ?",
                                   [original]).fetchone()
            sources_repo.save_source(con, {
                **base, "format": fmt, "encoding": enc, "duplicate_of": original,
                "event_count": 0, "checkpoint_bytes": 0, "checkpoint_line": 0,
            })
            result.files_duplicate += 1
            result.changes.append({"path": f.path, "action": "duplicate", "events": 0})
            continue

        if row is None:
            action, start_line, kept = "new", 0, 0
        elif row["duplicate_of"] is not None or f.size < (row["size"] or 0):
            action, start_line, kept = "rewritten", 0, 0
            events_repo.delete_for_source(con, source_id)
        else:
            action, start_line, kept = "appended", row["checkpoint_line"], row["event_count"]

        text, encoding = decode(data)
        fmt = detect_format(f.path, text)
        ctx = ParseContext(
            host=f.server,
            component="/".join(p for p in (f.application, f.component) if p) or None,
            default_date=infer_default_date([text]) or fallback_date,
        )
        new_events = [e for e in parse(fmt, text, ctx) if e.line_start > start_line]
        newest = events_repo.newest_ts_for_source(con, source_id) if action == "appended" else None
        count, last_line = writer.add_file(source_id, new_events, newest_before=newest)

        sources_repo.save_source(con, {
            **base, "format": fmt, "encoding": encoding, "duplicate_of": None,
            "event_count": kept + count,
            "checkpoint_bytes": 0 if f.compressed else f.size,
            "checkpoint_line": max(start_line, last_line),
        })
        setattr(result, f"files_{action}", getattr(result, f"files_{action}") + 1)
        result.changes.append({"path": f.path, "action": action, "events": count})

    writer.flush()
    result.events_written = writer.written
    if writer.written:
        result.duplicate_events = events_repo.mark_duplicates_since(con, first_new_id)
    if on_file:  # after the flush, so the events are already queryable
        for change in result.changes:
            on_file(change["path"], change["action"], change["events"])
    result.elapsed_s = round(time.perf_counter() - started, 2)
    return result
