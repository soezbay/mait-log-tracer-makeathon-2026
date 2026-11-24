"""Build a small test database from the demo scenario files only (seconds instead of a minute).

Usage (from backend/):
    python -m uv run python scripts/make_fixture.py            # writes FIXTURE_DB_PATH

Contains: the 24 Nov `creative` files of the servers in the JOB-2001/2003/2010 chains, the
October day with INC-01 (5 Oct) for the Teamcenter app and DB, and the `import_*` free-text
files of 6 Oct. Paths in `sources` are the same as in the real package, so the context
endpoint works as long as LOG_ROOT points to the real package.
"""

import argparse
import shutil
import tempfile
from pathlib import Path

from logtracer.core.config import get_settings
from logtracer.ingest.full_ingest import full_ingest
from logtracer.storage.db import connect, init_schema
from logtracer.storage.repositories.events import events_summary

SCENARIO_SERVERS = (
    "mait_win03_cad_converter",      # JOB-2003 conversion, JOB-2010 missing reference
    "mait_win04_plm_sync",           # JOB-2003 FMS client upload denied
    "mait_linux1_teamcenter_app",    # JOB-2003 FSC + workflow, JOB-2010 SOA, INC-01
    "mait_win02_dispatcher_worker",  # JOB-2001 clock skew
    "mait_linux2_teamcenter_db",     # INC-01 dependency
)
FILE_PATTERNS = (
    "creative_2026-11-24.*",          # scenario day, no _runNN copies
    "2026-10-05.ki-integriert.jsonl",  # INC-01 day
    "import_*.log",                    # free-text scenario of 6 Oct (no _runNN copies)
)


def select_files(log_root: Path) -> list[Path]:
    files: list[Path] = []
    for server in SCENARIO_SERVERS:
        logs = log_root / server / "logs"
        for pattern in FILE_PATTERNS:
            files.extend(p for p in logs.rglob(pattern) if "_run" not in p.name)
    return sorted(set(files))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", help="override FIXTURE_DB_PATH")
    args = parser.parse_args()
    settings = get_settings()
    out = Path(args.out) if args.out else settings.fixture_db_path

    files = select_files(settings.log_root)
    with tempfile.TemporaryDirectory(prefix="logtracer-fixture-") as tmp:
        tmp_root = Path(tmp)
        for src in files:
            dst = tmp_root / src.relative_to(settings.log_root)
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
        for server in SCENARIO_SERVERS:
            info = settings.log_root / server / "server_info.json"
            if info.is_file():
                shutil.copy2(info, tmp_root / server / "server_info.json")

        out.parent.mkdir(parents=True, exist_ok=True)
        out.unlink(missing_ok=True)
        con = connect(out)
        init_schema(con)
        result = full_ingest(con, tmp_root, default_tz=settings.default_timezone)
        summary = events_summary(con)
        con.close()

    print(f"Fixture written to {out}")
    print(f"  files: {result.files}, events: {result.events}, "
          f"duplicates: {result.duplicate_events}, elapsed: {result.elapsed_s} s")
    print(f"  levels: {summary['levels']}")


if __name__ == "__main__":
    main()
