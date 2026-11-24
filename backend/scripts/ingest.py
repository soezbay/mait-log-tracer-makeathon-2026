"""Ingest the log package into DuckDB.

Usage (from backend/, with the API server stopped: only one process may write the DB):
    python -m uv run python scripts/ingest.py --scan-only

Currently implemented: scan, read, file fingerprint and duplicate detection (fills `servers`
and `sources`). Parsing into `events` follows in the next steps.
"""

import argparse
import json

from logtracer.core.config import get_settings
from logtracer.ingest.pipeline import scan_sources
from logtracer.storage.db import connect, init_schema
from logtracer.storage.repositories.sources import scan_summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--scan-only", action="store_true",
                        help="only scan files and detect duplicates (parsing not implemented yet)")
    parser.add_argument("--db", help="override DB_PATH, e.g. :memory:")
    args = parser.parse_args()

    settings = get_settings()
    con = connect(args.db or settings.db_path)
    init_schema(con)

    print(f"Scanning {settings.log_root} …")
    result = scan_sources(con, settings.log_root)
    summary = scan_summary(con)
    summary["elapsed_s"] = result.elapsed_s
    summary["bytes_decompressed_unique"] = result.bytes_decompressed_unique
    summary["errors"] = result.errors
    print(json.dumps(summary, indent=2, default=str))

    if not args.scan_only:
        print("Note: parsing into `events` is not implemented yet; ran the scan only.")
    con.close()


if __name__ == "__main__":
    main()
