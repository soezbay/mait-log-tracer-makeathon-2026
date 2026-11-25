
from datetime import datetime

import duckdb

from logtracer.normalize.clock import (
    apply_clock_correction,
    calculate_offset,
    correct_timestamp,
)


def test_positive_clock_offset():
    timestamp = datetime(2026, 11, 24, 10, 5)

    corrected = correct_timestamp(timestamp, 300)

    assert corrected == datetime(2026, 11, 24, 10, 0)


def test_negative_clock_offset():
    timestamp = datetime(2026, 11, 24, 9, 55)

    corrected = correct_timestamp(timestamp, -300)

    assert corrected == datetime(2026, 11, 24, 10, 0)


def test_calculate_offset():
    server = datetime(2026, 11, 24, 10, 5)
    reference = datetime(2026, 11, 24, 10, 0)

    assert calculate_offset(server, reference) == 300


def test_database_clock_correction():
    con = duckdb.connect(":memory:")

    con.execute("""
        CREATE TABLE events (
            id BIGINT,
            host VARCHAR,
            ts_utc TIMESTAMP,
            clock_offset_s DOUBLE
        )
    """)

    con.execute("""
        INSERT INTO events VALUES
        (1, 'cad', '2026-11-24 10:05:00', 0.0),
        (2, 'cad', '2026-11-24 10:06:00', 0.0),
        (3, 'dispatcher', '2026-11-24 10:00:00', 0.0)
    """)

    result = apply_clock_correction(con, 'cad', 300)

    assert result["events_updated"] == 2

    rows = con.execute("""
        SELECT id, ts_utc, clock_offset_s
        FROM events
        ORDER BY id
    """).fetchall()

    assert rows[0][1] == datetime(2026, 11, 24, 10, 0)
    assert rows[1][1] == datetime(2026, 11, 24, 10, 1)
    assert rows[2][1] == datetime(2026, 11, 24, 10, 0)

    # Reapplying the same total offset should not
    # shift timestamps again.
    apply_clock_correction(con, 'cad', 300)

    after = con.execute("""
        SELECT ts_utc
        FROM events
        WHERE id = 1
    """).fetchone()

    assert after[0] == datetime(2026, 11, 24, 10, 0)

    con.close()
