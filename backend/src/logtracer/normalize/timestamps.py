"""Timestamps -> naive UTC datetimes.

Parsers deliver ISO 8601 text: with `Z` or an offset when the source states its time zone,
without one otherwise (e.g. `import_*.log`). Times without a zone are interpreted in
DEFAULT_TIMEZONE and flagged with tz_assumed. Clock correction per host is P2's job
(normalize/clock.py) and happens later on ts_utc.
"""

from datetime import UTC, datetime
from functools import lru_cache
from zoneinfo import ZoneInfo


@lru_cache(maxsize=8)
def _zone(name: str) -> ZoneInfo:
    return ZoneInfo(name)


def to_utc(ts: str | None, default_tz: str = "UTC") -> tuple[datetime | None, bool]:
    """Return (naive UTC datetime, tz_assumed). Unparseable or missing input gives (None, False)."""
    if not ts:
        return None, False
    try:
        parsed = datetime.fromisoformat(ts.strip())
    except ValueError:
        return None, False
    if parsed.tzinfo is None:
        aware = parsed.replace(tzinfo=_zone(default_tz))
        return aware.astimezone(UTC).replace(tzinfo=None), True
    return parsed.astimezone(UTC).replace(tzinfo=None), False
