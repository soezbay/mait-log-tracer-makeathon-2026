"""Turn parsed RawEvents into normalized `events` rows and write them in batches.

Shared by the full ingest and the incremental ingest.
"""

import json
from datetime import datetime

import duckdb

from logtracer.ingest.models import RawEvent
from logtracer.normalize.dedupe import LateDetector, fingerprint
from logtracer.normalize.levels import normalize_level
from logtracer.normalize.timestamps import to_utc
from logtracer.storage.repositories import events as events_repo


class EventWriter:
    def __init__(self, con: duckdb.DuckDBPyConnection, next_id: int, batch_size: int = 50_000,
                 default_tz: str = "UTC") -> None:
        self.con = con
        self.next_id = next_id
        self.batch_size = batch_size
        self.default_tz = default_tz
        self.batch = events_repo.new_batch()
        self.written = 0

    @property
    def pending(self) -> int:
        return len(self.batch["id"])

    def add_file(self, source_id: int, events: list[RawEvent],
                 newest_before: datetime | None = None) -> tuple[int, int]:
        """Queue all events of one file. Returns (event_count, last_line)."""
        late = LateDetector()
        if newest_before is not None:
            late.is_late(newest_before)  # continue late detection after a checkpoint
        last_line = 0
        b = self.batch
        for ev in events:
            ts_utc, tz_assumed = to_utc(ev.ts, self.default_tz)
            b["id"].append(self.next_id)
            b["source_id"].append(source_id)
            b["line_start"].append(ev.line_start)
            b["line_end"].append(ev.line_end)
            b["ts_raw"].append(ev.ts_raw)
            b["ts_utc"].append(ts_utc)
            b["tz_assumed"].append(tz_assumed)
            b["clock_offset_s"].append(0.0)
            b["ingest_seq"].append(self.next_id)
            b["host"].append(ev.host)
            b["component"].append(ev.component)
            b["level"].append(normalize_level(ev.level_raw))
            b["level_raw"].append(ev.level_raw)
            b["event_id"].append(ev.event_id)
            b["job_id"].append(ev.job_id)
            b["trace_id"].append(ev.trace_id)
            b["session_id"].append(ev.session_id)
            b["message"].append(ev.message)
            b["attrs"].append(json.dumps(ev.attrs) if ev.attrs else None)
            b["template_id"].append(None)
            b["fingerprint"].append(fingerprint(ev.host, ev.event_id, ts_utc, ev.message))
            b["duplicate_of"].append(None)
            b["is_late"].append(late.is_late(ts_utc))
            b["parse_error"].append(ev.parse_error)
            b["raw"].append(ev.raw)
            self.next_id += 1
            last_line = max(last_line, ev.line_end)
            if self.pending >= self.batch_size:
                self.flush()
                b = self.batch
        return len(events), last_line

    def flush(self) -> None:
        self.written += events_repo.insert_batch(self.con, self.batch)
        self.batch = events_repo.new_batch()
