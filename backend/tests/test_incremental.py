"""Incremental ingest with checkpoints, watcher and the /ingest endpoints."""

import asyncio
import os
import shutil
import time

import pytest
from fastapi.testclient import TestClient

from logtracer.core.config import Settings
from logtracer.ingest.full_ingest import full_ingest
from logtracer.ingest.incremental import incremental_ingest
from logtracer.ingest.watcher import LogWatcher
from logtracer.main import create_app
from logtracer.services.ingest_service import IngestManager
from logtracer.storage.db import connect, init_schema


def kv(i: int, minute: int = 0, level: str = "INFO") -> str:
    return (f"2026-11-25T09:{minute:02d}:{i % 60:02d}Z {level} host=mait_linux1 component=os/network "
            f"event_id=E-{i:05d} job_id=JOB-{i} | message {i}\n")


CSV_HEADER = "timestamp;level;host;component;event_id;job_id;message\n"


def csv_row(i: int) -> str:
    return (f"2026-11-25T10:00:{i:02d}Z;ERROR;mait_win01;dispatcher/core;C-{i};JOB-{i};"
            f'"failure {i}"\n')


@pytest.fixture
def env(tmp_path):
    root = tmp_path / "pkg"
    comp = root / "mait_linux1" / "logs" / "os" / "network"
    comp.mkdir(parents=True)
    (root / "mait_linux1" / "server_info.json").write_text('{"os_family": "Linux"}', "utf-8")
    (comp / "2026-11-25.log").write_text(kv(1) + kv(2), encoding="utf-8")
    con = connect(":memory:")
    init_schema(con)
    full_ingest(con, root)
    return con, root, comp


def count(con, where="TRUE"):
    return con.execute(f"SELECT count(*) FROM events WHERE {where}").fetchone()[0]


def bump_mtime(path):
    st = path.stat()
    os.utime(path, (st.st_atime + 5, st.st_mtime + 5))


def test_unchanged_files_are_skipped(env):
    con, root, _ = env
    res = incremental_ingest(con, root)
    assert (res.files_checked, res.files_unchanged, res.events_written) == (1, 1, 0)


def test_new_file_is_ingested(env):
    con, root, comp = env
    (comp / "2026-11-25_new.log").write_text(kv(10) + kv(11) + kv(12), encoding="utf-8")
    res = incremental_ingest(con, root)
    assert (res.files_new, res.events_written) == (1, 3)
    assert count(con) == 5
    src = con.execute("SELECT event_count, checkpoint_line, format FROM sources "
                      "WHERE path LIKE '%_new.log'").fetchone()
    assert src == (3, 3, "kv_log")


def test_appended_lines_only_add_new_events(env):
    con, root, comp = env
    log = comp / "2026-11-25.log"
    with log.open("a", encoding="utf-8") as fh:
        fh.write(kv(3, minute=1) + kv(4, minute=1))
    res = incremental_ingest(con, root, paths=[log])
    assert (res.files_appended, res.events_written) == (1, 2)
    assert count(con) == 4
    lines = [r[0] for r in con.execute("SELECT line_start FROM events ORDER BY id").fetchall()]
    assert lines == [1, 2, 3, 4]
    assert con.execute("SELECT event_count, checkpoint_line FROM sources").fetchone() == (4, 4)


def test_appended_csv_keeps_header_mapping(env):
    con, root, _ = env
    comp = root / "mait_win01" / "logs" / "dispatcher" / "core"
    comp.mkdir(parents=True)
    path = comp / "x.csv"
    path.write_text(CSV_HEADER + csv_row(1), encoding="utf-8")
    incremental_ingest(con, root)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(csv_row(2))
    res = incremental_ingest(con, root, paths=[path])
    assert res.events_written == 1
    assert con.execute("SELECT job_id, level FROM events WHERE event_id = 'C-2'").fetchone() == (
        "JOB-2", "ERROR")


def test_rewritten_file_replaces_its_events(env):
    con, root, comp = env
    log = comp / "2026-11-25.log"
    log.write_text(kv(7), encoding="utf-8")  # shorter than before
    bump_mtime(log)
    res = incremental_ingest(con, root, paths=[log])
    assert res.files_rewritten == 1
    assert [r[0] for r in con.execute("SELECT event_id FROM events").fetchall()] == ["E-00007"]


def test_copy_of_existing_file_is_a_duplicate(env):
    con, root, comp = env
    shutil.copy(comp / "2026-11-25.log", comp / "2026-11-25_run01.log")
    res = incremental_ingest(con, root)
    assert (res.files_duplicate, res.events_written) == (1, 0)
    assert con.execute("SELECT count(*) FROM sources WHERE duplicate_of IS NOT NULL"
                       ).fetchone()[0] == 1


def test_same_events_in_new_file_are_flagged_duplicates(env):
    con, root, comp = env
    (comp / "other.log").write_text(kv(2) + kv(99), encoding="utf-8")  # E-00002 already known
    res = incremental_ingest(con, root)
    assert (res.events_written, res.duplicate_events) == (2, 1)


def test_watcher_reports_changed_files(tmp_path):
    seen: list = []
    watcher = LogWatcher(tmp_path, seen.extend, debounce_s=0.3)
    watcher.start()
    try:
        target = tmp_path / "srv" / "logs" / "a" / "b"
        target.mkdir(parents=True)
        (target / "new.log").write_text("x\n", encoding="utf-8")
        (target / "README.md").write_text("ignored", encoding="utf-8")
        deadline = time.monotonic() + 5
        while not seen and time.monotonic() < deadline:
            time.sleep(0.05)
    finally:
        watcher.stop()
    names = {p.name for p in seen}
    assert "new.log" in names and "README.md" not in names


def test_manager_runs_and_publishes(env):
    con, root, comp = env
    settings = Settings(_env_file=None, auto_extract=False, log_root=root, db_path=":memory:")
    manager = IngestManager(con, settings)

    async def scenario():
        queue = manager.subscribe()
        (comp / "late.log").write_text(kv(20), encoding="utf-8")
        assert manager.start("incremental") is True
        events = []
        while not events or events[-1][0] not in ("done", "error"):
            events.append(await asyncio.wait_for(queue.get(), timeout=10))
        manager.unsubscribe(queue)
        return events

    events = asyncio.run(scenario())
    kinds = [e[0] for e in events]
    assert kinds[0] == "started" and "new_file" in kinds and kinds[-1] == "done"
    assert events[-1][1]["events_written"] == 1
    manager.wait(timeout=10)  # the analysis runs after "done"
    assert manager.state["running"] is False
    assert manager.analysis["error"] is None and manager.analysis["counts"] is not None


def test_rescan_picks_up_changes_without_watcher_and_stays_quiet(env):
    con, root, comp = env
    settings = Settings(_env_file=None, auto_extract=False, log_root=root, db_path=":memory:")
    manager = IngestManager(con, settings)

    async def scenario():
        queue = manager.subscribe()
        manager.start_rescans(0.2)
        try:
            await asyncio.sleep(0.8)  # several rescans, nothing changed
            assert queue.empty() and manager.state["last_result"] is None
            log = comp / "2026-11-25.log"
            with log.open("a", encoding="utf-8") as fh:
                fh.write(kv(40, minute=5))
            bump_mtime(log)
            events = []
            while not events or events[-1][0] != "done":
                events.append(await asyncio.wait_for(queue.get(), timeout=10))
            return events
        finally:
            manager.stop_rescans()
            manager.unsubscribe(queue)

    events = asyncio.run(scenario())
    assert [e[0] for e in events] == ["new_file", "done"]  # no "started" for a quiet rescan
    assert events[-1][1]["files_appended"] == 1
    assert count(con, "job_id = 'JOB-40'") == 1


def test_ingest_endpoints(tmp_path, env):
    _, root, comp = env
    db = tmp_path / "api.duckdb"
    con = connect(db)
    init_schema(con)
    full_ingest(con, root)
    con.close()
    settings = Settings(_env_file=None, auto_extract=False, log_root=root, db_path=db, watch_enabled=False,
                        auto_analysis=False)
    with TestClient(create_app(settings)) as client:
        assert client.get("/api/ingest/status").json()["running"] is False
        (comp / "added.log").write_text(kv(30) + kv(31), encoding="utf-8")
        started = client.post("/api/ingest", json={"mode": "incremental"})
        assert started.status_code == 202 and started.json()["mode"] == "incremental"
        client.app.state.ingest.wait(timeout=10)
        status = client.get("/api/ingest/status").json()
        assert status["running"] is False and status["last_result"]["events_written"] == 2
        assert client.get("/api/events", params={"job_id": "JOB-30"}).json()["total"] == 1
        assert client.post("/api/ingest", json={"mode": "nope"}).status_code == 422
