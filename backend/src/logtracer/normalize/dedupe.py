"""Event-level deduplication.

The fingerprint identifies the same log entry even if it appears in several files that are
not byte-identical (e.g. the same events in different formats or re-exported files).
Duplicates are flagged in SQL after the insert (storage/repositories/events.py), never deleted.
"""

import hashlib
from datetime import datetime

# An entry this many seconds older than the newest entry seen before it in the same file
# counts as a late entry.
LATE_TOLERANCE_S = 60.0


def fingerprint(host: str | None, event_id: str | None, ts_utc: datetime | None,
                message: str | None) -> str:
    key = "\x1f".join([
        host or "",
        event_id or "",
        ts_utc.isoformat() if ts_utc else "",
        message or "",
    ])
    return hashlib.sha1(key.encode("utf-8")).hexdigest()


class LateDetector:
    """Flags entries that are clearly older than an earlier entry of the same file."""

    def __init__(self, tolerance_s: float = LATE_TOLERANCE_S) -> None:
        self.tolerance_s = tolerance_s
        self.newest: datetime | None = None

    def is_late(self, ts_utc: datetime | None) -> bool:
        if ts_utc is None:
            return False
        if self.newest is None or ts_utc > self.newest:
            self.newest = ts_utc
            return False
        return (self.newest - ts_utc).total_seconds() > self.tolerance_s
