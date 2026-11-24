"""Ingest orchestration: scan → read → fingerprint → (parse, normalize, dedupe: next steps) → DuckDB."""

import gzip
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

import duckdb

from logtracer.ingest.fingerprint import DuplicateIndex, sha256
from logtracer.ingest.reader import decode, read_bytes
from logtracer.ingest.scanner import scan
from logtracer.storage.repositories import sources as sources_repo
from logtracer.storage.repositories.sources import SourceRow


@dataclass
class ScanResult:
    elapsed_s: float
    bytes_decompressed_unique: int
    errors: list[tuple[str, str]] = field(default_factory=list)


def scan_sources(con: duckdb.DuckDBPyConnection, log_root: Path) -> ScanResult:
    """Full scan: fill `servers` and `sources`, mark byte-identical copies via duplicate_of.

    Unique files are decoded once to record their encoding. Duplicates are not decoded.
    """
    started = time.perf_counter()
    servers, files = scan(log_root)
    now = datetime.now(UTC).replace(tzinfo=None)

    index = DuplicateIndex()
    encoding_of: dict[int, str | None] = {}
    rows: list[SourceRow] = []
    errors: list[tuple[str, str]] = []
    unique_bytes = 0

    for source_id, f in enumerate(files, start=1):
        digest: str | None = None
        encoding: str | None = None
        original: int | None = None
        try:
            data = read_bytes(f.abs_path)
            digest = sha256(data)
            original = index.add(digest, source_id)
            if original is None:
                _, encoding = decode(data)
                unique_bytes += len(data)
            else:
                encoding = encoding_of.get(original)
        except (OSError, EOFError, gzip.BadGzipFile) as exc:
            errors.append((f.path, f"{type(exc).__name__}: {exc}"))
        encoding_of[source_id] = encoding
        rows.append(
            SourceRow(
                source_id=source_id,
                path=f.path,
                server=f.server,
                application=f.application,
                component=f.component,
                format=None,  # set by the format detector (next step)
                encoding=encoding,
                compressed=f.compressed,
                sha256=digest,
                size=f.size,
                mtime=f.mtime,
                duplicate_of=original,
                ingested_at=now,
            )
        )

    sources_repo.replace_servers(con, servers)
    sources_repo.replace_sources(con, rows)
    return ScanResult(
        elapsed_s=round(time.perf_counter() - started, 2),
        bytes_decompressed_unique=unique_bytes,
        errors=errors,
    )
