"""Parse all unique sources: detect the format, run the parser, collect statistics.

Writing the events into DuckDB (with normalization and event dedupe) is the next step; this
module already records the detected format in `sources.format`.
"""

import collections
import re
import time
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path

import duckdb

from logtracer.ingest.detector import detect_format
from logtracer.ingest.models import ParseContext, RawEvent
from logtracer.ingest.parsers import parse
from logtracer.ingest.reader import read_text
from logtracer.storage.repositories import sources as sources_repo

_DATE = re.compile(r"\b(\d{4}-\d\d-\d\d)[ T]\d\d:\d\d")


@dataclass
class ParsedFile:
    source_id: int
    path: str
    format: str
    events: list[RawEvent]


@dataclass
class ParseStats:
    files: int = 0
    events: int = 0
    multiline_events: int = 0
    parse_errors: int = 0
    time_only_events: int = 0
    elapsed_s: float = 0.0
    default_date: str | None = None
    by_format: dict = field(default_factory=lambda: collections.defaultdict(lambda: {"files": 0, "events": 0, "parse_errors": 0}))
    levels: collections.Counter = field(default_factory=collections.Counter)
    error_samples: list[tuple[str, int, str, str]] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "files": self.files,
            "events": self.events,
            "multiline_events": self.multiline_events,
            "parse_errors": self.parse_errors,
            "time_only_events": self.time_only_events,
            "default_date_for_time_only_lines": self.default_date,
            "elapsed_s": self.elapsed_s,
            "by_format": dict(self.by_format),
            "levels_raw": dict(self.levels.most_common()),
            "error_samples": self.error_samples,
        }


def _component(application: str | None, component: str | None) -> str | None:
    return "/".join(p for p in (application, component) if p) or None


def infer_default_date(texts: list[str]) -> str | None:
    """Most common calendar date in files that contain time-only lines (e.g. import_*.log)."""
    dates = collections.Counter(d for text in texts for d in _DATE.findall(text))
    return dates.most_common(1)[0][0] if dates else None


def iter_parsed_sources(con: duckdb.DuckDBPyConnection, log_root: Path) -> Iterator[ParsedFile]:
    """Yield the parsed events of every unique source (duplicates are skipped)."""
    rows = con.execute(
        "SELECT source_id, path, server, application, component FROM sources "
        "WHERE duplicate_of IS NULL ORDER BY source_id"
    ).fetchall()

    # Free-text files may contain lines with only a time of day; take the date from the
    # dated free-text files of the package (all import_* files belong to the same scenario day).
    freetext_texts = [
        read_text(log_root / path)[0] for _, path, *_ in rows
        if Path(path).name.startswith("import_")
    ]
    default_date = infer_default_date(freetext_texts)

    for source_id, path, server, application, component in rows:
        text, _encoding = read_text(log_root / path)
        fmt = detect_format(path, text)
        ctx = ParseContext(host=server, component=_component(application, component),
                           default_date=default_date)
        yield ParsedFile(source_id, path, fmt, parse(fmt, text, ctx))


def dry_run(con: duckdb.DuckDBPyConnection, log_root: Path, max_samples: int = 15) -> ParseStats:
    """Parse everything without writing events; store formats; return statistics."""
    started = time.perf_counter()
    stats = ParseStats()
    formats: dict[int, str] = {}
    for parsed in iter_parsed_sources(con, log_root):
        formats[parsed.source_id] = parsed.format
        stats.files += 1
        bucket = stats.by_format[parsed.format]
        bucket["files"] += 1
        bucket["events"] += len(parsed.events)
        for event in parsed.events:
            stats.events += 1
            stats.levels[event.level_raw] += 1
            if event.line_end > event.line_start:
                stats.multiline_events += 1
            if event.attrs.get("time_only"):
                stats.time_only_events += 1
                stats.default_date = stats.default_date or (event.ts or "")[:10] or None
            if event.parse_error:
                stats.parse_errors += 1
                bucket["parse_errors"] += 1
                if len(stats.error_samples) < max_samples:
                    stats.error_samples.append(
                        (parsed.path, event.line_start, event.parse_error, event.raw[:160])
                    )
    sources_repo.set_formats(con, formats)
    stats.elapsed_s = round(time.perf_counter() - started, 2)
    return stats
