"""P2 analysis on the real schema: groups, correlations, incidents, anomalies, clock, API."""

from datetime import datetime, timedelta

import duckdb
import pytest
from fastapi.testclient import TestClient

from logtracer.analysis.anomalies import build_anomalies
from logtracer.analysis.correlation import build_correlations
from logtracer.analysis.error_groups import build_error_groups
from logtracer.analysis.incidents import build_incidents
from logtracer.analysis.jobs import build_jobs
from logtracer.analysis.pipeline import is_needed, run_analysis
from logtracer.analysis.problems import atomic
from logtracer.analysis.templates import build_templates
from logtracer.core.config import Settings
from logtracer.main import create_app
from logtracer.normalize.clock import apply_declared_offsets
from logtracer.storage.db import connect, init_schema

T0 = datetime(2026, 11, 24, 10, 0)


@pytest.fixture
def con():
    connection = duckdb.connect(":memory:")
    init_schema(connection)
    connection.execute("INSERT INTO sources (source_id, path, server) VALUES (1, 's/logs/a.log', 's')")
    yield connection
    connection.close()


def add(con, message, *, at=0.0, level="ERROR", host="server1", component="database", job=None,
        trace=None, attrs="{}", duplicate_of=None):
    """Insert one event `at` seconds after T0 and return its id."""
    pk = con.execute("SELECT coalesce(max(id), 0) + 1 FROM events").fetchone()[0]
    ts = T0 + timedelta(seconds=at)
    con.execute(
        "INSERT INTO events (id, source_id, line_start, line_end, ts_utc, ingest_seq, host, component,"
        " level, job_id, trace_id, message, attrs, duplicate_of, raw)"
        " VALUES (?, 1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [pk, pk, pk, ts, pk, host, component, level, job, trace, message, attrs, duplicate_of, message])
    return pk


def rows(con, sql):
    return con.execute(sql).fetchall()


# --- groups -------------------------------------------------------------------------------


def test_groups_count_originals_and_take_the_first_event_as_id(con):
    first = add(con, "Connection failed")
    add(con, "Connection failed", at=60)
    add(con, "Connection failed", at=90, duplicate_of=first)
    add(con, "Request accepted", level="INFO")
    result = build_error_groups(con)
    assert result == {"events_processed": 2, "groups_created": 1}
    assert rows(con, "SELECT group_id, count, level, status FROM error_groups") == \
        [(first, 2, "ERROR", "failed")]
    assert rows(con, "SELECT count(*) FROM group_members") == [(2,)]


def test_messages_that_are_mostly_normal_are_no_problem(con):
    for i in range(20):
        add(con, "Job heartbeat", at=i, level="INFO")
    add(con, "Job heartbeat", at=30, level="ERROR")
    add(con, "Disk full", at=31)
    assert build_error_groups(con)["groups_created"] == 1


def test_numbers_do_not_split_a_group_but_identifiers_do(con):
    add(con, "Queue depth increased to 125; new requests delayed", level="WARN")
    add(con, "Queue depth increased to 130; new requests delayed", level="WARN", at=5)
    add(con, "Timeout during INC-01")
    add(con, "Timeout during INC-02", at=5)
    assert build_error_groups(con)["groups_created"] == 3


def test_a_long_pause_starts_a_new_group(con):
    first = add(con, "Disk full")
    add(con, "Disk full", at=3600)
    later = add(con, "Disk full", at=3600 * 24)
    build_error_groups(con)
    assert rows(con, "SELECT group_id, count FROM error_groups ORDER BY 1") == \
        [(first, 2), (later, 1)]


@pytest.mark.parametrize(("message", "level", "status"), [
    ("Temporary slowdown; retry completed successfully; no lost work", "WARN", "recovered"),
    ("Transient retry recovered", "ERROR", "recovered"),
    ("Retry scheduled", "WARN", "unknown"),
    ("Upload rejected", "ERROR", "failed"),
])
def test_group_status(con, message, level, status):
    add(con, message, level=level)
    build_error_groups(con)
    assert rows(con, "SELECT status FROM error_groups") == [(status,)]


# --- templates ------------------------------------------------------------------------------


def test_templates_are_written_for_all_originals(con):
    for i, user in enumerate((101, 202, 303)):
        add(con, f"Connection failed for user {user}", at=i)
    result = build_templates(con, baseline_day=T0.date())
    assert result["templates_created"] == 1
    assert rows(con, "SELECT count, in_baseline FROM templates") == [(3, True)]
    assert rows(con, "SELECT count(*) FROM events WHERE template_id IS NULL") == [(0,)]


def test_templates_keep_incident_numbers_apart(con):
    for n in (1, 2, 3):
        add(con, f"Downstream timeout/retry during INC-0{n}; dependency=mait_linux{n}", at=n)
    assert build_templates(con)["templates_created"] == 3


# --- correlations and incidents --------------------------------------------------------------


def chain(con, job="JOB-2003", start=0, suffix=""):
    """win04 denies the upload, the server rejects it, the publish fails."""
    return [
        add(con, "Result upload denied", at=start, host="win04", component="fcc", job=job + suffix),
        add(con, "Upload rejected", at=start + 4, host="linux1", component="fsc", job=job + suffix),
        add(con, "Publish failed", at=start + 8, host="linux1", component="wf", job=job + suffix),
    ]


def test_shared_job_links_groups_once_however_many_runs(con):
    a, b, c = chain(con)
    chain(con, suffix="-R01", start=1)
    build_error_groups(con)
    assert build_correlations(con)["correlations_inserted"] == 3
    assert rows(con, "SELECT group_a, group_b, kind, link_key, lag_s FROM correlations ORDER BY 1, 2") \
        == [(a, b, "hard", "job_id=JOB-2003", 4.0), (a, c, "hard", "job_id=JOB-2003", 8.0),
            (b, c, "hard", "job_id=JOB-2003", 4.0)]
    # Running again rebuilds the same links.
    build_correlations(con)
    assert rows(con, "SELECT count(*) FROM correlations") == [(3,)]


def test_same_job_number_much_later_is_not_linked(con):
    add(con, "Reference missing", job="JOB-2010", component="a")
    add(con, "Exception", job="JOB-2010", component="b", at=4800)
    build_error_groups(con)
    assert build_correlations(con)["correlations_inserted"] == 0


def test_incident_starts_with_the_earliest_group(con):
    first, *_ = members = chain(con)
    other = add(con, "Disk full", host="other", job="JOB-1")
    build_error_groups(con)
    build_correlations(con)
    assert build_incidents(con) == {"incidents_created": 2, "groups_processed": 4}
    assert rows(con, "SELECT title, group_ids, hosts, status, confidence FROM incidents "
                f"WHERE incident_id = {first}") == \
        [("Result upload denied", members, ["linux1", "win04"], "failed", 0.7)]
    assert rows(con, f"SELECT root_group_id FROM incidents WHERE incident_id = {other}") == [(other,)]


def test_named_dependency_is_the_trigger_even_if_it_logs_later(con):
    add(con, "Downstream timeout; dependency=db1", host="app", job="J")
    trigger = add(con, "Connection pool exhausted", host="db1", job="J", at=20)
    build_error_groups(con)
    build_correlations(con)
    build_incidents(con)
    assert rows(con, "SELECT root_group_id, title, confidence FROM incidents") == \
        [(trigger, "Connection pool exhausted", 0.9)]


def test_separate_incidents_stay_separate_over_time(con):
    chain(con, job="JOB-1")
    chain(con, job="JOB-2", start=86400)
    run_analysis(con)
    assert rows(con, "SELECT len(group_ids) FROM incidents") == [(3,), (3,)]


def test_groups_without_ids_are_linked_by_time_only_weakly(con):
    add(con, "License timeout", host="a")
    add(con, "Export failed", host="b", at=10)
    add(con, "Much later", host="c", at=100)
    add(con, "Has a job", host="d", at=12, job="JOB-1")
    run_analysis(con)
    assert rows(con, "SELECT kind, link_key FROM correlations") == [("soft", "time")]
    assert sorted(rows(con, "SELECT len(group_ids), confidence FROM incidents")) == \
        [(1, 0.3), (1, 0.3), (2, 0.5)]


def test_successful_retries_alone_are_no_incident(con):
    for host in ("a", "b"):
        add(con, "Temporary slowdown; retry completed successfully", level="WARN", host=host, job="J")
    run_analysis(con)
    assert rows(con, "SELECT (SELECT count(*) FROM error_groups), (SELECT count(*) FROM incidents)") \
        == [(2, 0)]


def test_chain_that_ends_with_a_recovery_is_recovered(con):
    add(con, "Downstream timeout; retry scheduled", job="SYNC-312")
    add(con, "Transient retry recovered", job="SYNC-312", at=4)
    run_analysis(con)
    assert rows(con, "SELECT title, status FROM incidents") == \
        [("Downstream timeout; retry scheduled", "recovered")]


def test_rerun_after_new_events_leaves_no_stale_links(con):
    chain(con)
    run_analysis(con)
    before = rows(con, "SELECT group_id FROM error_groups ORDER BY 1")
    add(con, "Earlier problem", at=-5000, host="new", job="JOB-9")
    run_analysis(con)
    assert set(before) <= set(rows(con, "SELECT group_id FROM error_groups"))  # stable IDs
    assert rows(con, """SELECT count(*) FROM correlations k WHERE NOT EXISTS (
        SELECT 1 FROM group_members a JOIN events x ON x.id = a.event_pk
        JOIN group_members b ON b.group_id = k.group_b JOIN events y ON y.id = b.event_pk
        WHERE a.group_id = k.group_a AND x.job_id = y.job_id)""") == [(0,)]


def test_failed_step_keeps_the_old_result(con, monkeypatch):
    chain(con)
    run_analysis(con)

    def broken(_):
        raise RuntimeError("boom")

    monkeypatch.setattr("logtracer.analysis.pipeline.STEPS",
                        (("error_groups", lambda c: c.execute("DELETE FROM error_groups") and {}),
                         ("broken", broken)))
    with pytest.raises(RuntimeError):
        run_analysis(con)
    assert rows(con, "SELECT count(*) FROM error_groups") == [(3,)]
    with atomic(con):  # no transaction is left open
        con.execute("SELECT 1")


def test_analysis_is_needed_only_without_results(con):
    assert not is_needed(con)
    add(con, "Request accepted", level="INFO")
    assert is_needed(con)
    run_analysis(con)
    assert not is_needed(con)


# --- anomalies ------------------------------------------------------------------------------


def test_burst_is_one_anomaly_and_a_second_run_changes_nothing(con):
    for i in range(12):
        add(con, "Disk full", at=i)
    for _ in range(2):
        assert build_anomalies(con)["anomalies_detected"] == 1
    (count, kind, score), = rows(con, "SELECT count(*), any_value(kind), any_value(score) FROM anomalies")
    assert (count, kind, score) == (1, "rate_spike", 2.4)  # 12 errors, threshold 5


def test_few_errors_are_no_anomaly(con):
    for i in range(4):
        add(con, "Disk full", at=i)
    assert build_anomalies(con)["anomalies_detected"] == 0


def test_usual_error_rate_is_no_anomaly_but_a_spike_is(con):
    for window in range(143):  # 8 errors in every 10 minutes are normal here
        for i in range(8):
            add(con, "Disk full", at=window * 600 + i)
    spike = 143 * 600
    for i in range(40):
        add(con, "Disk full", at=spike + i)
    build_anomalies(con)
    last = rows(con, "SELECT window_start FROM anomalies ORDER BY window_start DESC LIMIT 1")
    assert last == [(T0 + timedelta(seconds=spike),)]
    assert rows(con, "SELECT count(*) FROM anomalies")[0][0] == 2  # the start and the spike


def test_spikes_in_a_row_are_one_anomaly(con):
    for window in range(3):
        for i in range(6):
            add(con, "Disk full", at=window * 600 + i)
    build_anomalies(con)
    assert rows(con, "SELECT window_start, window_end, details->>'observed_errors' FROM anomalies") == \
        [(T0, T0 + timedelta(minutes=30), "18")]


# --- clock ----------------------------------------------------------------------------------


def test_only_events_with_a_declared_offset_are_moved(con):
    moved = add(con, "Worker failed", attrs='{"clock_offset_seconds": -94}')
    other = add(con, "Same server, right time")
    for _ in range(2):  # a second run does not move it again
        apply_declared_offsets(con)
    assert dict(rows(con, "SELECT id, ts_utc FROM events")) == \
        {moved: T0 + timedelta(seconds=94), other: T0}
    assert rows(con, f"SELECT clock_offset_s FROM events WHERE id = {moved}") == [(-94.0,)]


def test_clock_correction_restores_the_order_of_the_chain(con):
    add(con, "Worker failed", at=-86, job="JOB-2001", host="w", attrs='{"clock_offset_seconds": -94}')
    trigger = add(con, "Time service unsynchronized", level="WARN", job="JOB-2001", host="w")
    run_analysis(con)
    assert rows(con, "SELECT root_group_id FROM incidents") == [(trigger,)]


# --- jobs -----------------------------------------------------------------------------------


def jobs(con):
    build_jobs(con)
    columns = "job_id, trace_id, runs, status, events, errors, warnings, problem, len(hosts)"
    return rows(con, f"SELECT {columns} FROM jobs ORDER BY first_ts, job_pk")


def test_runs_of_a_job_are_one_job_across_servers(con):
    chain(con)
    chain(con, suffix="-R01", start=1)
    assert jobs(con) == [("JOB-2003", None, 2, "failed", 6, 6, 0, "Result upload denied", 2)]
    assert jobs(con) == jobs(con)  # rebuilding changes nothing


def test_a_long_pause_starts_a_new_job_but_not_within_a_trace(con):
    add(con, "Request accepted", level="INFO", job="JOB-1")
    add(con, "Request accepted", level="INFO", job="JOB-1", at=1700)
    add(con, "Request accepted", level="INFO", job="JOB-1", at=9000)
    add(con, "Request accepted", level="INFO", job="JOB-2", trace="T")
    add(con, "Request accepted", level="INFO", job="JOB-2", trace="T", at=9000)
    add(con, "Request accepted", level="INFO", job="JOB-2", trace="T2", at=9000)
    assert sorted((j, t, n) for j, t, _, _, n, *_ in jobs(con) if j == "JOB-1") == \
        [("JOB-1", None, 1), ("JOB-1", None, 2)]
    assert sorted((t, n) for j, t, _, _, n, *_ in jobs(con) if j == "JOB-2") == [("T", 2), ("T2", 1)]


def test_lines_without_trace_belong_to_the_only_trace_of_the_job(con):
    add(con, "Worker failed", job="JOB-2001", trace="T")
    add(con, "Time service unsynchronized", job="JOB-2001", level="WARN", at=4)
    add(con, "Same number much later", job="JOB-2001", at=9000)
    add(con, "Two traces", job="JOB-3", trace="A")
    add(con, "Two traces", job="JOB-3", trace="B", at=1)
    add(con, "Two traces", job="JOB-3", at=2)
    assert sorted((j, t or "", n) for j, t, _, _, n, *_ in jobs(con)) == [
        ("JOB-2001", "", 1), ("JOB-2001", "T", 2), ("JOB-3", "", 1), ("JOB-3", "A", 1), ("JOB-3", "B", 1)]


def test_harmless_messages_do_not_make_a_job_fail_or_recover(con):
    for i in range(30):
        add(con, "Transient retry recovered", at=i, level="INFO", job=f"OK-{i}")
    add(con, "Transient retry recovered", at=40, level="ERROR", job="JOB-00-00000")
    assert {status for _, _, _, status, *_ in jobs(con)} == {"ok"}


@pytest.mark.parametrize(("lines", "status"), [
    ([("Started", "INFO"), ("Disk full", "ERROR")], "failed"),
    ([("Slow response", "WARN")], "warning"),
    ([("Timeout; retry scheduled", "ERROR"), ("Retry succeeded", "WARN")], "recovered"),
    ([("Retry succeeded", "WARN"), ("Disk full", "ERROR")], "failed"),
    ([("Started", "INFO")], "ok"),
])
def test_job_status(con, lines, status):
    for i, (message, level) in enumerate(lines):
        add(con, message, level=level, at=i, job="J-1")
    assert [row[3] for row in jobs(con)] == [status]


def test_first_error_is_the_problem_even_after_a_warning(con):
    add(con, "Slow response", level="WARN", job="J-1")
    add(con, "Disk full", at=5, job="J-1")
    assert jobs(con)[0][7] == "Disk full"


def test_jobs_link_to_their_incident_and_ignore_events_without_job(con):
    first, *_ = chain(con)
    add(con, "No job here", at=5000)
    run_analysis(con)
    assert rows(con, "SELECT job_id, incident_id, problem_event_id FROM jobs") == \
        [("JOB-2003", first, first)]


# --- API ------------------------------------------------------------------------------------


@pytest.fixture
def client(tmp_path):
    db = tmp_path / "a.duckdb"
    con = connect(db)
    init_schema(con)
    con.execute("INSERT INTO sources (source_id, path, server) VALUES (1, 'win04/logs/a.log', 'win04')")
    chain(con)
    chain(con, suffix="-R01", start=1)
    add(con, "Disk full", host="other", at=90000)
    con.close()
    with TestClient(create_app(Settings(_env_file=None, auto_extract=False, db_path=db,
                                        log_root=tmp_path))) as c:
        c.app.state.ingest.wait(timeout=20)  # the analysis runs on start, because it is missing
        yield c


def test_analysis_runs_on_start_and_on_request(client):
    status = client.get("/api/analysis/status").json()
    assert status["running"] is False and status["error"] is None
    assert status["counts"]["incidents"] == 2 and status["finished_at"].endswith("Z")
    assert client.post("/api/analysis/run").status_code == 202
    client.app.state.ingest.wait(timeout=20)
    assert client.get("/api/analysis/stats").json()["counts"]["incidents"] == 2


def test_incident_list_and_filters(client):
    page = client.get("/api/analysis/incidents").json()
    assert (page["total"], page["limit"], page["offset"]) == (2, 50, 0)
    newest, upload = page["items"]
    assert newest["title"] == "Disk full"
    assert upload["title"] == "Result upload denied"
    assert upload["jobs"] == [{"job_id": "JOB-2003", "runs": 2}]
    assert (upload["group_count"], upload["event_count"]) == (3, 6)
    assert upload["first_ts"] == "2026-11-24T10:00:00Z"

    def titles(**params):
        return [i["title"] for i in client.get("/api/analysis/incidents", params=params).json()["items"]]

    assert titles(server="win04") == ["Result upload denied"]
    assert titles(q="job-2003") == titles(q="publish failed") == ["Result upload denied"]
    assert titles(event_id=upload["root_event_id"]) == ["Result upload denied"]
    assert titles(**{"from": "2026-11-25T00:00:00Z"}) == ["Disk full"]
    assert titles(status="recovered") == []
    assert client.get("/api/analysis/incidents", params={"status": "x"}).status_code == 422


def test_incident_detail_has_steps_links_and_source_lines(client):
    incident = client.get("/api/analysis/incidents", params={"server": "win04"}).json()["items"][0]
    detail = client.get(f"/api/analysis/incidents/{incident['incident_id']}").json()
    assert [(s["message"], s["is_root"], s["count"]) for s in detail["steps"]] == [
        ("Result upload denied", True, 2), ("Upload rejected", False, 2), ("Publish failed", False, 2)]
    assert detail["steps"][0]["source_path"] == "win04/logs/a.log"
    assert len(detail["links"]) == 3
    assert client.get("/api/analysis/incidents/999").status_code == 404


def test_groups_anomalies_graph_and_trace(client):
    groups = client.get("/api/analysis/groups").json()
    assert groups["total"] == 4 and groups["items"][0]["event_ids"]
    assert client.get("/api/analysis/anomalies").json()["items"] == []
    incident = client.get("/api/analysis/incidents", params={"server": "win04"}).json()["items"][0]
    graph = client.get("/api/analysis/graph", params={"incident_id": incident["incident_id"]}).json()
    assert len(graph["nodes"]) == 3 and len(graph["edges"]) == 3
    assert len(client.get("/api/analysis/graph").json()["nodes"]) == 4
    assert client.get("/api/analysis/graph", params={"incident_id": 999}).status_code == 404
    trace = client.get("/api/trace/JOB-2003").json()
    assert trace["total"] == 3 and trace["items"][0]["message"] == "Result upload denied"
    assert client.get("/api/trace/nothing").status_code == 404


def test_jobs_api_filters_sorts_and_pages(client):
    page = client.get("/api/jobs").json()
    assert page["total"] == 1 and page["by_status"] == {"failed": 1} and page["servers"] == []
    job = page["items"][0]
    assert (job["job_id"], job["runs"], job["status"], job["errors"]) == ("JOB-2003", 2, "failed", 6)
    assert job["hosts"] == ["linux1", "win04"] and job["incident_id"] == job["problem_event_id"]
    assert job["first_ts"] == "2026-11-24T10:00:00Z"

    def total(**params):
        return client.get("/api/jobs", params=params).json()["total"]

    assert total(status="failed") == total(server="win04") == total(q="job-2003") == 1
    assert total(q="publish") == 0 and total(q="upload denied") == 1
    assert total(status="ok") == total(server="nope") == total(conversion=True) == 0
    assert total(**{"from": "2026-11-25T00:00:00Z"}) == 0 and total(to="2026-11-24T10:00:01Z") == 1
    assert client.get("/api/jobs", params={"sort": "x"}).status_code == 422
    for sort in ("problems", "recent", "oldest", "duration", "errors", "job"):
        assert total(sort=sort) == 1
    # The status counts ignore the status filter, so the UI can show all of them.
    assert client.get("/api/jobs", params={"status": "ok"}).json()["by_status"] == {"failed": 1}


def test_job_detail_and_its_events(client):
    pk = client.get("/api/jobs").json()["items"][0]["job_pk"]
    assert client.get(f"/api/jobs/{pk}").json()["job_id"] == "JOB-2003"
    events = client.get(f"/api/jobs/{pk}/events").json()
    assert events["total"] == 6 and events["items"][0]["message"] == "Result upload denied"
    assert {e["job_id"] for e in events["items"]} == {"JOB-2003", "JOB-2003-R01"}
    assert client.get(f"/api/jobs/{pk}/events", params={"problems": True, "limit": 2}).json()["total"] == 6
    assert client.get("/api/jobs/999999").status_code == 404
    assert client.get("/api/jobs/999999/events").status_code == 404
