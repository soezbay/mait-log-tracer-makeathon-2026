
from logtracer.analysis.anomalies import detect_spikes


def test_normal_error_counts():
    counts = [2, 3, 2, 4, 3, 2, 3]

    result = detect_spikes(counts)

    assert result == []


def test_detect_error_spike():
    baseline = [2, 3, 2, 4, 3, 2, 3]

    # Compare a new interval against a normal baseline.
    new_count = 35

    result = detect_spikes(baseline + [new_count], sensitivity=2.0)

    assert len(result) == 1
    assert result[0]["count"] == 35


def test_empty_counts():
    assert detect_spikes([]) == []



import duckdb

from logtracer.analysis.anomalies import build_anomalies


def test_database_anomaly_detection():
    con = duckdb.connect(":memory:")

    con.execute("""
        CREATE TABLE events (
            id BIGINT,
            host VARCHAR,
            component VARCHAR,
            level VARCHAR,
            ts_utc TIMESTAMP,
            duplicate_of BIGINT
        )
    """)

    con.execute("""
        CREATE TABLE anomalies (
            anomaly_id INTEGER PRIMARY KEY,
            host VARCHAR,
            component VARCHAR,
            kind VARCHAR,
            window_start TIMESTAMP,
            window_end TIMESTAMP,
            score DOUBLE,
            details JSON
        )
    """)

    # Five normal minutes, then one error spike.
    counts = [1, 2, 1, 2, 1, 12]

    event_id = 1

    for minute, count in enumerate(counts):
        for _ in range(count):
            timestamp = f"2026-11-24 10:{minute:02d}:00"

            con.execute("""
                INSERT INTO events
                VALUES (?, ?, ?, ?, ?, NULL)
            """, [
                event_id,
                "server1",
                "database",
                "ERROR",
                timestamp
            ])

            event_id += 1

    result = build_anomalies(con)

    assert result["anomalies_detected"] == 1
    assert result["anomalies_inserted"] == 1

    stored = con.execute("""
        SELECT kind FROM anomalies
    """).fetchone()

    assert stored == ("rate_spike",)

    # Running twice must not insert the same anomaly.
    second = build_anomalies(con)
    assert second["anomalies_inserted"] == 0

    con.close()
