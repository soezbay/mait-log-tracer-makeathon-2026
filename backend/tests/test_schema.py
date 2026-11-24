import json

import pytest

from logtracer.storage.db import connect, init_schema

EXPECTED_TABLES = {
    # P1
    "servers", "sources", "events",
    # P2
    "templates", "error_groups", "group_members", "anomalies", "correlations", "incidents",
    # P3
    "hypotheses", "llm_calls", "chat_messages",
}


@pytest.fixture
def con():
    con = connect(":memory:")
    init_schema(con)
    yield con
    con.close()


def test_all_tables_exist(con):
    tables = {row[0] for row in con.execute("SELECT table_name FROM information_schema.tables").fetchall()}
    assert EXPECTED_TABLES <= tables


def test_init_schema_is_idempotent(con):
    init_schema(con)  # second run must not fail


def test_source_and_event_roundtrip(con):
    # Real event from the JOB-2003 chain (fms/fsc on mait_linux1_teamcenter_app).
    con.execute(
        "INSERT INTO sources (source_id, path, server, application, component, format, encoding) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        [
            812,
            "mait_linux1_teamcenter_app/logs/fms/fsc/creative_2026-11-24.txt",
            "mait_linux1_teamcenter_app", "fms", "fsc", "bracket_json", "utf-8",
        ],
    )
    source_id = con.execute("SELECT source_id FROM sources").fetchone()[0]
    assert source_id == 812

    con.execute(
        "INSERT INTO events (id, source_id, line_start, line_end, ts_raw, ts_utc, ingest_seq, "
        "host, component, level, level_raw, event_id, job_id, message, attrs, raw) "
        "VALUES (1002, ?, 29, 29, '2026-11-24T08:30:08Z', TIMESTAMP '2026-11-24 08:30:08', 1, "
        "'mait_linux1_teamcenter_app', 'fms/fsc', 'ERROR', 'ERROR', 'CREATIVE-00045771', "
        "'JOB-2003', 'Upload rejected; access policy lacks target volume write permission', "
        "?, 'raw line')",
        [source_id, json.dumps({"origin": "test"})],
    )
    row = con.execute(
        "SELECT job_id, level, attrs->>'origin', clock_offset_s, is_late FROM events"
    ).fetchone()
    assert row == ("JOB-2003", "ERROR", "test", 0.0, False)


def test_events_allow_updates_from_analysis(con):
    # P2 sets template_id on existing events; this must work without key conflicts.
    con.execute(
        "INSERT INTO events (id, source_id, line_start, line_end, ingest_seq, raw) "
        "VALUES (1, 1, 1, 1, 1, 'a'), (2, 1, 2, 2, 2, 'b')"
    )
    con.execute("UPDATE events SET template_id = 7")
    assert con.execute("SELECT count(*) FROM events WHERE template_id = 7").fetchone()[0] == 2
