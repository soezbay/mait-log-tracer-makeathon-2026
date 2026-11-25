"""Build a STAND-IN DuckDB from the real log package so P3 can test the assistant before P1's ingest is done.

    python scripts/make_standin_db.py --logs ../MAIT_Makeathon_Logpaket --db ../data/standin.duckdb --force

Reads .jsonl(.gz), .log, .txt and .csv (best effort, formats as described in plan.en.md section 3); skips
.xml, README.md and server_info.json. Byte-identical copies (_runNN) are linked, not parsed twice. Writes the
tables of the real storage/schema.sql (P1), plus naive error groups (same host + component + message with
numbers masked). It does NOT do clock correction, Drain3 templates, anomalies, correlations or incidents:
those come from P2. Never writes into the log folder.
"""
from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import io
import json
import os
import re
import sys
from collections import Counter
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import duckdb
import pandas as pd

from logtracer.storage.db import init_schema

LEVELS = {"WARNING": "WARN", "CRITICAL": "FATAL", "SEVERE": "FATAL", "TRACE": "DEBUG", "ERR": "ERROR", "INFORMATION": "INFO"}
LINE_RE = re.compile(r"^(?P<ts>\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:[.,]\d+)?(?:Z|[+-]\d{2}:?\d{2})?)\s+\[?(?P<lvl>[A-Za-z]+)\]?\s+(?P<rest>.*)$")
KV_RE = re.compile(r'(\w+)=("[^"]*"|\S+)')
CONT_RE = re.compile(r"^(\s+|at |Caused by|\.\.\. |[\w.$]+(Exception|Error)\b)")
ALIASES = {
    "ts": ("timestamp", "ts", "time", "@timestamp", "datetime"),
    "level": ("level", "severity", "lvl", "loglevel"),
    "host": ("host", "hostname", "server"),
    "component": ("component", "logger", "source"),
    "event_id": ("event_id", "eventid", "event", "code"),
    "job_id": ("job_id", "jobid", "job"),
    "trace_id": ("trace_id", "traceid"),
    "session_id": ("session_id", "sessionid", "session"),
    "message": ("message", "msg", "text"),
}


def norm_level(v: Any) -> str:
    s = str(v or "INFO").strip().upper()
    return LEVELS.get(s, s)


def parse_ts(raw: Any) -> datetime | None:
    if raw is None:
        return None
    try:
        dt = datetime.fromisoformat(str(raw).strip().replace("Z", "+00:00").replace(",", "."))
    except ValueError:
        return None
    return dt.astimezone(UTC).replace(tzinfo=None) if dt.tzinfo else dt


def from_mapping(d: dict[str, Any], line: int, end: int | None = None) -> dict[str, Any]:
    low = {str(k).lower(): v for k, v in d.items()}
    out: dict[str, Any] = {}
    used: set[str] = set()
    for field, names in ALIASES.items():
        for n in names:
            if n in low and low[n] not in (None, ""):
                out[field] = low[n]
                used.add(n)
                break
    out["attrs"] = {k: v for k, v in low.items() if k not in used}
    out["line"], out["line_end"] = line, end or line
    return out


def parse_jsonl(text: str) -> Iterable[dict[str, Any]]:
    for i, line in enumerate(text.splitlines(), 1):
        if line.strip():
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                yield {"_bad": True}
                continue
            yield from_mapping(obj, i) if isinstance(obj, dict) else {"_bad": True}


def parse_text_log(text: str) -> Iterable[dict[str, Any]]:
    """.log (key=value) and .txt (key=value | {json}); stack-trace lines are attached to the previous event."""
    cur: dict[str, Any] | None = None
    for i, line in enumerate(text.splitlines(), 1):
        m = LINE_RE.match(line)
        if m:
            if cur:
                yield cur
            rest = m["rest"]
            head, sep, tail = rest.partition(" | ")
            if sep and KV_RE.search(head):
                kv = {k: v.strip('"') for k, v in KV_RE.findall(head)}
                body = tail
            elif KV_RE.fullmatch(head.strip() or "-"):
                kv, body = {k: v.strip('"') for k, v in KV_RE.findall(head)}, ""
            else:
                kv, body = {}, rest
            data: dict[str, Any] = {"timestamp": m["ts"], "level": m["lvl"], **kv}
            if body.lstrip().startswith("{"):
                try:
                    data.update(json.loads(body))
                except json.JSONDecodeError:
                    data["message"] = body
            else:
                data["message"] = body
            cur = from_mapping(data, i)
        elif cur and CONT_RE.match(line):
            cur["message"] = f"{cur.get('message', '')}\n{line}".strip()
            cur["line_end"] = i
        elif line.strip():
            yield {"_bad": True}
    if cur:
        yield cur


def parse_csv(text: str) -> Iterable[dict[str, Any]]:
    reader = csv.reader(io.StringIO(text, newline=""), delimiter=";")
    header = next(reader, None)
    if not header:
        return
    header = [h.strip().lower() for h in header]
    prev = reader.line_num
    for row in reader:
        start, prev = prev + 1, reader.line_num
        if not any(row):
            continue
        yield from_mapping(dict(zip(header, row)), start, prev)


PARSERS = {".jsonl": parse_jsonl, ".log": parse_text_log, ".txt": parse_text_log, ".csv": parse_csv}


def read_file(path: Path) -> tuple[bytes, str, bool]:
    raw = path.read_bytes()
    gz = path.suffix == ".gz"
    if gz:
        raw = gzip.decompress(raw)
    try:
        return raw, raw.decode("utf-8-sig"), gz
    except UnicodeDecodeError:
        return raw, raw.decode("cp1252", errors="replace"), gz


def fmt_of(path: Path) -> str | None:
    suffixes = [s.lower() for s in path.suffixes]
    if suffixes[-1:] == [".gz"]:
        suffixes = suffixes[:-1]
    return suffixes[-1] if suffixes and suffixes[-1] in PARSERS else None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--logs", default=os.getenv("LOG_ROOT", "../MAIT_Makeathon_Logpaket"))
    ap.add_argument("--db", default="../data/standin.duckdb")
    ap.add_argument("--max-files", type=int, default=0, help="stop after N distinct files (0 = all)")
    ap.add_argument("--force", action="store_true", help="overwrite an existing DB file")
    args = ap.parse_args()

    root, db = Path(args.logs), Path(args.db)
    if not root.is_dir():
        print(f"Log folder not found: {root}", file=sys.stderr)
        return 1
    if db.exists():
        if not args.force:
            print(f"{db} exists. Use --force to rebuild it.", file=sys.stderr)
            return 1
        db.unlink()
    db.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(db))
    init_schema(con)

    seen_hash: dict[str, int] = {}
    seen_fp: dict[tuple, int] = {}
    stats: Counter = Counter()
    batch: list[dict[str, Any]] = []
    next_event = next_source = 1
    cols = ["id", "source_id", "line_start", "line_end", "ts_raw", "ts_utc", "ingest_seq", "host",
            "component", "level",
            "event_id", "job_id", "trace_id", "session_id", "message", "attrs", "duplicate_of", "raw"]

    def flush() -> None:
        nonlocal batch
        if batch:
            df = pd.DataFrame(batch, columns=cols)  # noqa: F841 (read by DuckDB)
            con.execute(f"INSERT INTO events ({','.join(cols)}) SELECT {','.join(cols)} FROM df")
            batch = []

    files = sorted(p for p in root.rglob("*") if p.is_file())
    for n, path in enumerate(files, 1):
        rel = path.relative_to(root).as_posix()
        fmt = fmt_of(path)
        if fmt is None:
            stats[f"skipped:{path.suffix or 'none'}"] += 1
            continue
        if args.max_files and stats["files_parsed"] >= args.max_files:
            break
        parts = rel.split("/")
        server = parts[0]
        application = parts[2] if len(parts) > 3 and parts[1] == "logs" else None
        path_component = "/".join(parts[3:-1]) if len(parts) > 4 and parts[1] == "logs" else None
        try:
            raw, text, gz = read_file(path)
        except (OSError, EOFError) as exc:
            stats["unreadable_files"] += 1
            print(f"  cannot read {rel}: {exc}", file=sys.stderr)
            continue
        digest = hashlib.sha256(raw).hexdigest()
        sid, next_source = next_source, next_source + 1
        dup = seen_hash.get(digest)
        con.execute(
            "INSERT INTO sources (source_id, path, server, application, component, format, compressed, sha256, size, duplicate_of) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [sid, rel, server, application, path_component, fmt.lstrip("."), gz, digest, len(raw), dup],
        )
        if dup is not None:
            stats["duplicate_files"] += 1
            continue
        seen_hash[digest] = sid
        stats["files_parsed"] += 1
        for rec in PARSERS[fmt](text):
            if rec.get("_bad"):
                stats[f"unparsed_lines:{fmt}"] += 1
                continue
            host = str(rec.get("host") or server)
            msg = str(rec.get("message") or "")
            ts = parse_ts(rec.get("ts"))
            level = norm_level(rec.get("level"))
            fp = (host, rec.get("event_id"), ts, msg)
            eid, next_event = next_event, next_event + 1
            dup_of = seen_fp.setdefault(fp, eid)
            batch.append({
                "id": eid, "source_id": sid, "line_start": rec["line"], "line_end": rec["line_end"],
                "ts_raw": str(rec.get("ts")), "ts_utc": ts, "ingest_seq": eid, "host": host,
                "component": str(rec.get("component") or path_component or application or ""),
                "level": level, "event_id": _s(rec.get("event_id")), "job_id": _s(rec.get("job_id")),
                "trace_id": _s(rec.get("trace_id")), "session_id": _s(rec.get("session_id")),
                "message": msg, "attrs": json.dumps(rec.get("attrs") or {}, ensure_ascii=False, default=str),
                "duplicate_of": None if dup_of == eid else dup_of,
                "raw": str(rec.get("raw") or msg),  # events.raw is NOT NULL in schema.sql
            })
            stats[f"events:{fmt}"] += 1
            if ts is None:
                stats["events_without_timestamp"] += 1
            if len(batch) >= 100_000:
                flush()
        if stats["files_parsed"] % 200 == 0:
            print(f"  {n}/{len(files)} files, {next_event - 1} events …")
    flush()

    # naive error groups (P2 replaces these with Drain3-based groups)
    con.execute("""
        CREATE TEMP TABLE masked AS
        SELECT id, host, component, ts_utc, message,
               regexp_replace(regexp_replace(message, '"[^"]*"', '"<s>"', 'g'), '[0-9]+', '<n>', 'g') AS tpl
        FROM events WHERE duplicate_of IS NULL AND upper(level) IN ('WARN','ERROR','FATAL')""")
    # error_groups has no title column: the group's text goes to templates (template_id = group_id)
    con.execute("""
        CREATE TEMP TABLE naive_groups AS
        SELECT dense_rank() OVER (ORDER BY host, component, tpl) AS group_id, host, component,
               any_value(message) AS title, min(ts_utc) AS first_ts, max(ts_utc) AS last_ts,
               count(*) AS n,
               CASE WHEN bool_or(message ILIKE '%recover%' OR message ILIKE '%retry succe%'
                                 OR message ILIKE '%successful%')
                    THEN 'recovered' ELSE 'unknown' END AS status
        FROM masked GROUP BY host, component, tpl""")
    con.execute("""
        INSERT INTO templates (template_id, template, count, first_seen, last_seen)
        SELECT group_id, title, n, first_ts, last_ts FROM naive_groups""")
    con.execute("""
        INSERT INTO error_groups (group_id, template_id, host, component, count, first_ts, last_ts, status)
        SELECT group_id, group_id, host, component, n, first_ts, last_ts, status FROM naive_groups""")
    con.execute("""
        INSERT INTO group_members (group_id, event_pk)
        SELECT g.group_id, m.id FROM masked m JOIN (
            SELECT dense_rank() OVER (ORDER BY host, component, tpl) AS group_id, host, component, tpl FROM masked GROUP BY host, component, tpl
        ) g USING (host, component, tpl)""")

    total = con.execute("SELECT count(*) FROM events").fetchone()[0]
    print(f"\nDone: {db}  ({total} events)")
    for k, v in sorted(stats.items()):
        print(f"  {k}: {v}")
    print("  levels:", dict(con.execute("SELECT level, count(*) FROM events GROUP BY 1 ORDER BY 2 DESC").fetchall()))
    print("  error groups:", con.execute("SELECT count(*) FROM error_groups").fetchone()[0])
    print(f"\nNext: set DB_PATH={db} in backend/.env and run  python scripts/ask.py \"...\"")
    con.close()
    return 0


def _s(v: Any) -> str | None:
    return None if v in (None, "") else str(v)


if __name__ == "__main__":
    raise SystemExit(main())
