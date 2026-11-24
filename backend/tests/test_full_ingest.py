import json

import pytest

from logtracer.ingest.full_ingest import full_ingest
from logtracer.storage.db import connect, init_schema
from logtracer.storage.repositories.events import events_summary

KV = (
    "2026-11-23T08:00:14Z WARN host=mait_linux1 component=os/network event_id=E-1 "
    "job_id=NORMAL-1 | Transient latency; retry succeeded\n"
    "2026-11-23T08:00:37Z INFO host=mait_linux1 component=os/network event_id=E-2 "
    "job_id=NORMAL-2 | Operation completed duration_ms=487\n"
    "2026-11-23T07:50:00Z ERROR host=mait_linux1 component=os/network event_id=E-3 "
    "job_id=NORMAL-3 | Arrived late\n"
)
SAME_EVENT_AS_JSONL = json.dumps({
    "timestamp": "2026-11-23T08:00:14Z", "level": "WARN", "host": "mait_linux1",
    "component": "os/network", "event_id": "E-1", "job_id": "NORMAL-1",
    "message": "Transient latency; retry succeeded",
}) + "\n"
FREETEXT = "[2026-10-06 14:02:15] TC.ERROR - Workflow blocked\n[14:02:16] TC.RAC - ok\n"


@pytest.fixture
def log_root(tmp_path):
    srv = tmp_path / "mait_linux1"
    comp = srv / "logs" / "os" / "network"
    comp.mkdir(parents=True)
    (srv / "server_info.json").write_text('{"os_family": "Linux"}', encoding="utf-8")
    (comp / "2026-11-23.log").write_text(KV, encoding="utf-8")
    (comp / "2026-11-23_run01.log").write_text(KV, encoding="utf-8")  # byte copy, not parsed
    (comp / "2026-11-23.jsonl").write_text(SAME_EVENT_AS_JSONL, encoding="utf-8")
    tc = srv / "logs" / "teamcenter" / "workflow"
    tc.mkdir(parents=True)
    (tc / "import_sample.log").write_text(FREETEXT, encoding="utf-8")
    return tmp_path


def test_full_ingest_writes_events_with_origin(log_root):
    con = connect(":memory:")
    init_schema(con)
    result = full_ingest(con, log_root, batch_size=2)  # small batches on purpose
    assert result.files == 3  # the byte-identical copy is skipped
    assert result.events == 3 + 1 + 2

    row = con.execute(
        "SELECT s.path, e.line_start, e.level, e.job_id, e.attrs->>'duration_ms' "
        "FROM events e JOIN sources s USING (source_id) WHERE e.event_id = 'E-2'"
    ).fetchone()
    assert row == ("mait_linux1/logs/os/network/2026-11-23.log", 2, "INFO", "NORMAL-2", "487")


def test_full_ingest_dedupe_late_and_time_zone(log_root):
    con = connect(":memory:")
    init_schema(con)
    result = full_ingest(con, log_root)
    # E-1 appears in the .log and the .jsonl file (not byte-identical) -> one duplicate
    assert result.duplicate_events == 1
    assert con.execute(
        "SELECT count(*) FROM events WHERE event_id = 'E-1' AND duplicate_of IS NOT NULL"
    ).fetchone()[0] == 1
    # E-3 is 10 minutes older than the entry before it
    assert con.execute("SELECT is_late FROM events WHERE event_id = 'E-3'").fetchone()[0] is True
    # free-text times have no zone -> tz_assumed; time-only line gets the date of the file
    rows = con.execute(
        "SELECT strftime(ts_utc, '%Y-%m-%d %H:%M:%S'), tz_assumed, level FROM events "
        "WHERE component = 'teamcenter/workflow' ORDER BY line_start"
    ).fetchall()
    assert rows == [("2026-10-06 14:02:15", True, "ERROR"), ("2026-10-06 14:02:16", True, "INFO")]

    summary = events_summary(con)
    assert summary["events"] == 6 and summary["unparsed_events"] == 0
    sources = con.execute(
        "SELECT path, format, event_count, checkpoint_line FROM sources ORDER BY path"
    ).fetchall()
    assert ("mait_linux1/logs/os/network/2026-11-23.log", "kv_log", 3, 3) in sources
    assert ("mait_linux1/logs/os/network/2026-11-23_run01.log", "kv_log", 0, 0) in sources


def test_full_ingest_is_repeatable(log_root):
    con = connect(":memory:")
    init_schema(con)
    full_ingest(con, log_root)
    full_ingest(con, log_root)
    assert con.execute("SELECT count(*) FROM events").fetchone()[0] == 6
