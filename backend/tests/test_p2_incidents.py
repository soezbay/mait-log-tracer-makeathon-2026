
import duckdb

from logtracer.analysis.incidents import build_incidents


def test_incident_generation():
    con = duckdb.connect(":memory:")

    con.execute("""
        CREATE TABLE error_groups (
            group_id INTEGER,
            host VARCHAR,
            first_ts TIMESTAMP,
            last_ts TIMESTAMP,
            status VARCHAR
        )
    """)

    con.execute("""
        CREATE TABLE correlations (
            group_a INTEGER,
            group_b INTEGER,
            confidence DOUBLE
        )
    """)

    con.execute("""
        CREATE TABLE incidents (
            incident_id INTEGER PRIMARY KEY,
            title VARCHAR,
            first_ts TIMESTAMP,
            last_ts TIMESTAMP,
            status VARCHAR,
            hosts VARCHAR[],
            group_ids INTEGER[],
            root_group_id INTEGER,
            confidence DOUBLE
        )
    """)

    # Three related errors and one independent error.
    con.execute("""
        INSERT INTO error_groups VALUES
        (101, 'cad',
         '2026-11-24 10:00:00',
         '2026-11-24 10:01:00', 'unknown'),
        (102, 'dispatcher',
         '2026-11-24 10:00:12',
         '2026-11-24 10:02:00', 'unknown'),
        (103, 'teamcenter',
         '2026-11-24 10:00:25',
         '2026-11-24 10:03:00', 'unknown'),
        (104, 'platform',
         '2026-11-24 11:00:00',
         '2026-11-24 11:01:00', 'unknown')
    """)

    con.execute("""
        INSERT INTO correlations VALUES
        (101, 102, 0.8),
        (102, 103, 0.7)
    """)

    result = build_incidents(con)

    # Three linked groups form one incident.
    # The independent group forms another.
    assert result["incidents_created"] == 2
    assert result["groups_processed"] == 4

    rows = con.execute("""
        SELECT group_ids, root_group_id
        FROM incidents
        ORDER BY incident_id
    """).fetchall()

    assert any(
        set(ids) == {101, 102, 103} and root == 101
        for ids, root in rows
    )

    assert any(
        ids == [104] and root == 104
        for ids, root in rows
    )

    con.close()
