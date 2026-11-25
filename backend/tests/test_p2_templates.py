
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
