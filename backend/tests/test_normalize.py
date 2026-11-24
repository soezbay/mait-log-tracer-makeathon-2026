from datetime import datetime

from logtracer.normalize.dedupe import LateDetector, fingerprint
from logtracer.normalize.levels import normalize_level
from logtracer.normalize.timestamps import to_utc


def test_to_utc_with_zone():
    assert to_utc("2026-11-24T08:30:08Z") == (datetime(2026, 11, 24, 8, 30, 8), False)
    assert to_utc("2026-10-06T14:02:15.234Z") == (datetime(2026, 10, 6, 14, 2, 15, 234000), False)
    assert to_utc("2026-11-24T09:30:08+01:00") == (datetime(2026, 11, 24, 8, 30, 8), False)


def test_to_utc_without_zone_is_assumed():
    assert to_utc("2026-10-06T14:02:15.234") == (datetime(2026, 10, 6, 14, 2, 15, 234000), True)
    # Europe/Berlin is UTC+2 in summer time (6 Oct)
    assert to_utc("2026-10-06T14:02:15", "Europe/Berlin") == (datetime(2026, 10, 6, 12, 2, 15), True)


def test_to_utc_invalid():
    assert to_utc(None) == (None, False)
    assert to_utc("not a time") == (None, False)


def test_levels():
    assert [normalize_level(x) for x in ("INFO", "WARN", "WARNING", "ERROR", "DEBUG")] == [
        "INFO", "WARN", "WARN", "ERROR", "DEBUG"]
    assert normalize_level("Critical") == "FATAL"
    assert normalize_level("CRITICAL") == "FATAL"
    assert normalize_level("whatever") is None
    assert normalize_level(None) is None


def test_fingerprint_is_stable_and_field_sensitive():
    ts = datetime(2026, 11, 24, 8, 30, 8)
    a = fingerprint("h", "E-1", ts, "msg")
    assert a == fingerprint("h", "E-1", ts, "msg")
    assert a != fingerprint("h", "E-2", ts, "msg")
    assert a != fingerprint("h", "E-1", None, "msg")


def test_late_detector():
    late = LateDetector(tolerance_s=60)
    t = datetime(2026, 11, 24, 8, 0, 0)
    assert late.is_late(t) is False
    assert late.is_late(datetime(2026, 11, 24, 8, 5, 0)) is False
    assert late.is_late(datetime(2026, 11, 24, 8, 4, 30)) is False  # within tolerance
    assert late.is_late(datetime(2026, 11, 24, 8, 1, 0)) is True
    assert late.is_late(None) is False
