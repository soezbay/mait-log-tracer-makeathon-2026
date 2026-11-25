"""GET /api/suggestions on a small log tree: real errors, re-runs, noise and event context."""

import pytest
from fastapi.testclient import TestClient

from logtracer.core.config import Settings
from logtracer.ingest.full_ingest import full_ingest
from logtracer.main import create_app
from logtracer.storage.db import connect, init_schema

HOST = "mait_linux1_teamcenter_app"


def line(ts, level, job, message, component="fms/fsc", host=HOST):
    return f"{ts} [{level}] host={host} component={component} event_id=E-1 job_id={job} | " \
           f'{{"message": "{message}"}}\n'


REJECTED = "Upload rejected; access policy lacks target volume write permission"
TIMEOUT = "Downstream timeout/retry during INC-03; dependency=mait_win01_dispatcher_master"


def log_text():
    lines = [line("2026-11-24T08:30:00Z", "INFO", "JOB-2003", "Conversion succeeded")]
    lines += [line(f"2026-11-24T08:3{i}:08Z", "ERROR", f"JOB-2003{run}", REJECTED)
              for i, run in enumerate(["", "-R01", "-R02"])]
    # The same message is normal 30 times and an ERROR once: noise, no problem.
    lines += [line(f"2026-11-24T09:00:{i:02d}Z", "INFO", f"OK-{i}", "Cache lookup successful")
              for i in range(30)]
    lines.append(line("2026-11-24T09:01:00Z", "ERROR", "OK-99", "Cache lookup successful"))
    lines += [line(f"2026-10-11T11:40:{i:02d}Z", "ERROR", f"PLM-{i}", TIMEOUT) for i in range(2)]
    return "".join(sorted(lines))


def make_client(tmp_path, text):
    root = tmp_path / "logs"
    folder = root / HOST / "logs" / "fms" / "fsc"
    folder.mkdir(parents=True)
    (folder / "creative_2026-11-24.txt").write_text(text, encoding="utf-8")
    (root / HOST / "server_info.json").write_text('{"os_family": "Linux"}', encoding="utf-8")
    db = tmp_path / "test.duckdb"
    con = connect(db)
    init_schema(con)
    full_ingest(con, root)
    con.close()
    return TestClient(create_app(Settings(
        _env_file=None, log_root=root, db_path=db, auto_extract=False, watch_enabled=False)))


@pytest.fixture
def client(tmp_path):
    with make_client(tmp_path, log_text()) as c:
        yield c


def event_id(client, **filters):
    return client.get("/api/events", params=filters).json()["items"][0]["id"]


def by_kind(items):
    return {item["kind"]: item for item in items}


def test_suggestions_come_from_the_logs(client):
    body = client.get("/api/suggestions").json()
    assert (body["scope"], body["event_id"]) == ("logs", None)
    items = by_kind(body["items"])
    # Re-runs count as one job; the newest problem comes first.
    assert body["items"][0] == items["job"]
    assert items["job"]["question"] == "What caused the errors in JOB-2003?"
    assert items["job"]["reason"] == "3 errors, 3 runs, 1 server"
    assert items["job"]["last_ts"] == "2026-11-24T08:32:08Z"
    assert "INC-03" in items["incident"]["question"]
    assert items["server"]["question"] == f"Which problems did {HOST} have on 2026-11-24?"
    # The event id lets the UI open the log line behind a suggestion.
    assert client.get(f"/api/events/{items['job']['event_id']}").json()["message"] == REJECTED


def test_noise_is_never_offered_as_a_problem(client):
    items = client.get("/api/suggestions", params={"limit": 20}).json()["items"]
    noisy = [i for i in items if "Cache lookup" in i["question"] or i["job_id"] == "OK-99"]
    assert [i["kind"] for i in noisy] == ["noise"]
    assert noisy[0]["question"] == 'Are the ERROR entries "Cache lookup successful" harmless?'


def test_language_and_limit(client):
    items = client.get("/api/suggestions", params={"lang": "de", "limit": 1}).json()["items"]
    assert [i["question"] for i in items] == ["Was hat die Fehler in JOB-2003 verursacht?"]
    assert items[0]["reason"] == "3 Fehler, 3 Läufe, 1 Server"
    assert client.get("/api/suggestions", params={"lang": "fr"}).status_code == 422
    assert client.get("/api/suggestions", params={"limit": 0}).status_code == 422


def test_event_scope_asks_about_the_opened_error_and_its_job(client):
    pk = event_id(client, job_id="JOB-2003", level="ERROR")
    body = client.get("/api/suggestions", params={"event_id": pk}).json()
    assert (body["scope"], body["event_id"]) == ("event", pk)
    items = by_kind(body["items"])
    assert list(items) == ["event_error", "job_errors", "job_flow", "job_runs", "around"]
    assert items["event_error"]["question"] == \
        f'What caused "{REJECTED}" on {HOST} at 2026-11-24 08:30:08 UTC?'
    assert items["job_errors"]["reason"] == "1 error, 1 server"
    assert items["job_runs"]["reason"] == "3 runs"


def test_event_scope_of_a_rerun_names_the_job_family(client):
    pk = event_id(client, job_id="JOB-2003-R02")
    items = by_kind(client.get("/api/suggestions", params={"event_id": pk}).json()["items"])
    assert items["job_errors"]["question"] == "What caused the errors in JOB-2003-R02?"
    assert items["job_runs"]["question"] == \
        "Do the other runs of JOB-2003 show the same problem?"


def test_event_scope_treats_noise_and_normal_entries_differently(client):
    noisy = event_id(client, job_id="OK-99")
    items = by_kind(client.get("/api/suggestions", params={"event_id": noisy}).json()["items"])
    assert list(items) == ["event_noise", "job_flow", "around"]  # no "what caused" question
    normal = event_id(client, job_id="OK-3")
    items = by_kind(client.get("/api/suggestions", params={"event_id": normal}).json()["items"])
    assert list(items) == ["event_info", "job_flow", "around"]


def test_unknown_event_is_404(client):
    assert client.get("/api/suggestions", params={"event_id": 999999}).status_code == 404


def test_unusual_day_is_compared_with_days_without_errors(tmp_path):
    text = "".join(sorted(
        [line(f"2026-11-{day:02d}T08:00:00Z", "INFO", "OK-1", "Request accepted")
         for day in range(1, 6)]
        + [line(f"2026-11-04T10:00:{i:02d}Z", "ERROR", "JOB-1", f"Disk error {i}")
           for i in range(12)]))
    with make_client(tmp_path, text) as c:
        items = by_kind(c.get("/api/suggestions", params={"limit": 20}).json()["items"])
    assert items["day"]["question"] == "Why were there so many errors on 2026-11-04?"
    assert items["day"]["reason"] == "12 errors, 0 on a typical day"


def test_no_errors_means_no_suggestions(tmp_path):
    with make_client(tmp_path, line("2026-11-24T08:00:00Z", "INFO", "OK-1", "Fine")) as c:
        assert c.get("/api/suggestions").json()["items"] == []


def test_message_text_cannot_break_the_question(tmp_path):
    text = line("2026-11-24T08:00:00Z", "ERROR", "JOB-1", "Bad {field} in {0}") \
        + line("2026-11-24T08:01:00Z", "ERROR", "JOB-2", "x" * 300)
    with make_client(tmp_path, text) as c:
        first = c.get("/api/suggestions", params={"event_id": event_id(c, job_id="JOB-1")})
        assert "Bad {field} in {0}" in first.json()["items"][0]["question"]
        second = c.get("/api/suggestions", params={"event_id": event_id(c, job_id="JOB-2")})
        question = second.json()["items"][0]["question"]
        assert "…" in question and len(question) < 200
