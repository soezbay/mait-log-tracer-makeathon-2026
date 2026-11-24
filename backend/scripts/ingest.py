"""Ingest the log package into DuckDB.

Usage (from backend/, with the API server stopped: only one process may write the DB):
    python -m uv run python scripts/ingest.py --scan-only        # files, duplicates, encodings
    python -m uv run python scripts/ingest.py --parse-dry-run    # + detect formats, parse, statistics

Implemented: scan, read, file fingerprint and duplicate detection (fills `servers` and
`sources`), format detection and parsing (statistics only). Writing `events` follows next.
"""

import argparse
import json

from logtracer.core.config import get_settings
from logtracer.ingest.parse_run import dry_run
from logtracer.ingest.pipeline import scan_sources
from logtracer.storage.db import connect, init_schema
from logtracer.storage.repositories.sources import scan_summary


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

    print(f"Scanning {settings.log_root} …", flush=True)
    result = scan_sources(con, settings.log_root)
    summary = scan_summary(con)
    summary.pop("per_server")
    summary.update(elapsed_s=result.elapsed_s, errors=result.errors,
                   bytes_decompressed_unique=result.bytes_decompressed_unique)
    print(json.dumps({"scan": summary}, indent=2, default=str), flush=True)

    if args.parse_dry_run:
        print("Parsing unique files (dry run, no events written) …", flush=True)
        stats = dry_run(con, settings.log_root)
        print(json.dumps({"parse": stats.as_dict()}, indent=2, default=str))
    elif not args.scan_only:
        print("Note: writing `events` is not implemented yet. Use --parse-dry-run for parser stats.")
    con.close()


if __name__ == "__main__":
    main()
