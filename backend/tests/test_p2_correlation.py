
import duckdb

from logtracer.analysis.correlation import build_correlations


def test_cross_system_correlation():
    con = duckdb.connect(":memory:")

    con.execute("""
        CREATE TABLE events (
            id BIGINT,
            host VARCHAR,
            ts_utc TIMESTAMP,
            job_id VARCHAR,
            trace_id VARCHAR,
            duplicate_of BIGINT
        )
    """)

    con.execute("""
        CREATE TABLE group_members (
            group_id INTEGER,
            event_pk BIGINT
        )
    """)

    con.execute("""
        CREATE TABLE correlations (
            correlation_id INTEGER PRIMARY KEY,
            group_a INTEGER,
            group_b INTEGER,
            kind VARCHAR,
            link_key VARCHAR,
            lag_s DOUBLE,
            confidence DOUBLE
        )
    """)

    con.execute("""
        INSERT INTO events VALUES
        (1, 'cad', '2026-11-24 10:00:00',
         'JOB-2003', NULL, NULL),

        (2, 'dispatcher', '2026-11-24 10:00:12',
         'JOB-2003', NULL, NULL),

        (3, 'teamcenter', '2026-11-24 10:00:25',
         'JOB-2003', NULL, NULL),

        (4, 'platform', '2026-11-24 11:00:00',
         'JOB-9999', NULL, NULL)
    """)

    con.execute("""
        INSERT INTO group_members VALUES
        (101, 1),
        (102, 2),
        (103, 3),
        (104, 4)
    """)

    result = build_correlations(con)

    assert result["correlations_inserted"] == 3

    rows = con.execute("""
        SELECT group_a, group_b
        FROM correlations
        ORDER BY group_a, group_b
    """).fetchall()

    assert rows == [
        (101, 102),
        (101, 103),
        (102, 103),
    ]

    # Running twice should not duplicate relationships.
    second = build_correlations(con)

    assert second["correlations_inserted"] == 0

    con.close()
