
from logtracer.analysis.error_groups import classify_event


def test_error_classification():
    assert classify_event(
        "ERROR", "Database unavailable"
    ) == "error"

    assert classify_event(
        "WARN", "Connection taking too long"
    ) == "warning"

    assert classify_event(
        "INFO", "Request accepted"
    ) == "normal"

    assert classify_event(
        "INFO", "Workflow transition complete"
    ) == "normal"

    assert classify_event(
        None, "Connection failed"
    ) == "possible_error"

    assert classify_event(
        None, "Unknown event"
    ) == "unknown"



import duckdb

from logtracer.analysis.error_groups import build_error_groups


def test_database_error_grouping():
    # Create temporary database
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

    # Add sample log events
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

    group = con.execute(
        "SELECT count, level FROM error_groups"
    ).fetchone()

    assert group == (2, "ERROR")

    members = con.execute(
        "SELECT COUNT(*) FROM group_members"
    ).fetchone()

    assert members is not None
    assert members[0] == 2

    con.close()
