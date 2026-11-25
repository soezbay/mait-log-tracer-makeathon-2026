
import duckdb

from logtracer.analysis.templates import build_templates


def test_template_grouping():
    # Create a temporary database for testing
    con = duckdb.connect(":memory:")

    # Create example events table
    con.execute("""
        CREATE TABLE events (
            id BIGINT,
            message VARCHAR,
            ts_utc TIMESTAMP,
            duplicate_of BIGINT,
            template_id INTEGER
        )
    """)

    # Create templates table
    con.execute("""
        CREATE TABLE templates (
            template_id INTEGER,
            template VARCHAR,
            count BIGINT,
            first_seen TIMESTAMP,
            last_seen TIMESTAMP,
            in_baseline BOOLEAN
        )
    """)

    # Insert three example log messages
    con.execute("""
        INSERT INTO events VALUES
        (1, 'Connection failed for user 101',
         '2026-11-24 10:00:00', NULL, NULL),
        (2, 'Connection failed for user 202',
         '2026-11-24 10:01:00', NULL, NULL),
        (3, 'Connection failed for user 303',
         '2026-11-24 10:02:00', NULL, NULL)
    """)

    # Run your P2 Drain3 analysis
    result = build_templates(con)

    # Check the results
    assert result["events_processed"] == 3
    assert result["templates_created"] >= 1

    row = con.execute(
        "SELECT COUNT(*) FROM events WHERE template_id IS NOT NULL"
    ).fetchone()

    assert row is not None
    assert row[0] == 3

    con.close()

import duckdb

from logtracer.analysis.error_groups import build_error_groups


def test_database_error_grouping():
    con = duckdb.connect(":memory:")

    con.execute("""
        CREATE TABLE events (
            id BIGINT,
            template_id INTEGER,
            host VARCHAR,
            component VARCHAR,
            level VARCHAR,
            ts_utc TIMESTAMP,
            duplicate_of BIGINT
        )
    """)

    con.execute("""
        CREATE TABLE error_groups (
            group_id INTEGER PRIMARY KEY,
            template_id INTEGER,
            host VARCHAR,
            component VARCHAR,
            level VARCHAR,
            count BIGINT,
            first_ts TIMESTAMP,
            last_ts TIMESTAMP,
            status VARCHAR,
            sample_event_ids BIGINT[]
        )
    """)

    con.execute("""
        CREATE TABLE group_members (
            group_id INTEGER,
            event_pk BIGINT
        )
    """)

    con.execute("""
        INSERT INTO events VALUES
        (1, 100, 'server1', 'database',
         'ERROR', '2026-11-24 10:00:00', NULL),
        (2, 100, 'server1', 'database',
         'ERROR', '2026-11-24 10:01:00', NULL),
        (3, 200, 'server1', 'database',
         'INFO', '2026-11-24 10:02:00', NULL),
        (4, 100, 'server1', 'database',
         'ERROR', '2026-11-24 10:03:00', 1)
    """)

    result = build_error_groups(con)

    assert result["events_processed"] == 2
    assert result["groups_created"] == 1

    group = con.execute("""
        SELECT count, level
        FROM error_groups
    """).fetchone()

    assert group == (2, "ERROR")

    members = con.execute("""
        SELECT COUNT(*) FROM group_members
    """).fetchone()

    assert members is not None
    assert members[0] == 2

    con.close()
