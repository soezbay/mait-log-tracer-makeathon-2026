"""Ingest the log package into DuckDB.

Usage (from backend/, with the API server stopped: only one process may write the DB):
    python -m uv run python scripts/ingest.py                    # full ingest (default)
    python -m uv run python scripts/ingest.py --scan-only        # files, duplicates, encodings
    python -m uv run python scripts/ingest.py --parse-dry-run    # + formats and parser stats

The full ingest rebuilds `servers`, `sources` and `events`; the log files are only read.
"""

import argparse
import json

from logtracer.core.config import get_settings
from logtracer.ingest.full_ingest import full_ingest
from logtracer.ingest.parse_run import dry_run
from logtracer.ingest.pipeline import scan_sources
from logtracer.storage.db import connect, init_schema
from logtracer.storage.repositories.events import events_summary
from logtracer.storage.repositories.sources import scan_summary


def _print(title: str, data: dict) -> None:
    print(json.dumps({title: data}, indent=2, default=str), flush=True)


def _progress(done: int, total: int, events: int) -> None:
    print(f"  {done}/{total} files, {events:,} events", flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--scan-only", action="store_true",
                      help="only scan files and detect duplicates")
    mode.add_argument("--parse-dry-run", action="store_true",
                      help="scan, detect formats and parse all unique files without writing events")
    parser.add_argument("--db", help="override DB_PATH, e.g. :memory:")
    args = parser.parse_args()

    settings = get_settings()
    con = connect(args.db or settings.db_path)
    init_schema(con)
    print(f"Log package: {settings.log_root}\nDatabase:    {args.db or settings.db_path}",
          flush=True)

    if args.scan_only or args.parse_dry_run:
        result = scan_sources(con, settings.log_root)
        summary = scan_summary(con)
        summary.pop("per_server")
        summary.update(elapsed_s=result.elapsed_s, errors=result.errors)
        _print("scan", summary)
        if args.parse_dry_run:
            _print("parse", dry_run(con, settings.log_root).as_dict())
    else:
        result = full_ingest(con, settings.log_root, batch_size=settings.ingest_batch_size,
                             default_tz=settings.default_timezone, progress=_progress)
        scan = scan_summary(con)
        _print("ingest", {
            "files": scan["sources"],
            "unique_files": scan["unique_sources"],
            "parsed_files": result.files,
            "scan_errors": result.scan.errors,
            "elapsed_s": result.elapsed_s,
            **events_summary(con),
        })
    con.close()


if __name__ == "__main__":
    main()
