"""API tests for /stats, /sources, /events, /events/{id}, /events/{id}/context on a small log tree."""

import gzip
import json

import pytest
from fastapi.testclient import TestClient

from logtracer.core.config import Settings
from logtracer.ingest.full_ingest import full_ingest
from logtracer.main import create_app
from logtracer.storage.db import connect, init_schema

CSV = (
    "timestamp;level;host;component;event_id;job_id;message;duration_ms;session_id\r\n"
    "2026-11-24T08:30:00Z;INFO;mait_win03_cad_converter;converter/nx_jt;CREATIVE-00045769;JOB-2003;"
    '"Conversion succeeded; JT output=DEMO-301.jt checksum=abc123";;\r\n'
    "2026-11-24T11:01:00Z;ERROR;mait_win03_cad_converter;converter/nx_jt;CREATIVE-00045827;JOB-2010;"
    '"SyntheticConversionException: reference missing\r\n'
    "  at demo.converter.resolve(Resolver.java:82)\r\n"
    'Caused by: MissingReferenceException: DEMO-Seal-17/C";;\r\n'
)
TXT = (
    "2026-11-24T08:29:22Z [INFO] host=mait_linux1_teamcenter_app component=fms/fsc "
    'event_id=CREATIVE-00024668 job_id=OK-03156 | {"message": "Dataset transferred", '
    '"duration_ms": 343}\n'
    "2026-11-24T08:30:08Z [ERROR] host=mait_linux1_teamcenter_app component=fms/fsc "
    "event_id=CREATIVE-00045771 job_id=JOB-2003 | "
    '{"message": "Upload rejected; access policy lacks target volume write permission"}\n'
    "2026-11-24T08:30:38Z [INFO] host=mait_linux1_teamcenter_app component=fms/fsc "
    'event_id=CREATIVE-00024669 job_id=OK-07325 | {"message": "Dataset transferred"}\n'
)
GZ_JSONL = json.dumps({
    "timestamp": "2026-11-24T08:30:12Z", "level": "ERROR", "host": "mait_linux1_teamcenter_app",
    "component": "teamcenter/workflow", "event_id": "CREATIVE-00045772", "job_id": "JOB-2003",
    "message": "Publish task failed: no registered result; converter status=SUCCESS",
}) + "\n"


@pytest.fixture
def client(tmp_path):
    root = tmp_path / "logs"
    win = root / "mait_win03_cad_converter" / "logs" / "converter" / "nx_jt"
    win.mkdir(parents=True)
    (win / "creative_2026-11-24.csv").write_text(CSV, encoding="utf-8", newline="")
    (win / "creative_2026-11-24_run01.csv").write_text(CSV, encoding="utf-8", newline="")
    tc = root / "mait_linux1_teamcenter_app" / "logs"
    (tc / "fms" / "fsc").mkdir(parents=True)
    (tc / "fms" / "fsc" / "creative_2026-11-24.txt").write_text(TXT, encoding="utf-8")
    (tc / "teamcenter" / "workflow").mkdir(parents=True)
    (tc / "teamcenter" / "workflow" / "creative_2026-11-24.jsonl.gz").write_bytes(
        gzip.compress(GZ_JSONL.encode())
    )
    (root / "mait_linux1_teamcenter_app" / "server_info.json").write_text(
        '{"os_family": "Linux"}', encoding="utf-8")

    db = tmp_path / "test.duckdb"
    con = connect(db)
    init_schema(con)
    full_ingest(con, root)
    con.close()

    settings = Settings(_env_file=None, auto_extract=False, db_path=db, log_root=root)
    with TestClient(create_app(settings)) as c:
        yield c


def test_stats(client):
    body = client.get("/api/stats").json()
    assert body["sources"] == 4 and body["unique_sources"] == 3 and body["duplicate_sources"] == 1
    assert body["events"] == 6
    assert body["levels"] == {"DEBUG": 0, "INFO": 3, "WARN": 0, "ERROR": 3, "FATAL": 0}
    assert body["time_range"] == {"from": "2026-11-24T08:29:22Z", "to": "2026-11-24T11:01:00Z"}


def test_sources_filters(client):
    body = client.get("/api/sources", params={"duplicates": "true"}).json()
    assert body["total"] == 1
    assert body["items"][0]["path"].endswith("creative_2026-11-24_run01.csv")
    linux = client.get("/api/sources", params={"server": "mait_linux1_teamcenter_app"}).json()
    assert {s["os"] for s in linux["items"]} == {"Linux"}
    assert {s["format"] for s in linux["items"]} == {"bracket_json", "jsonl"}


def test_events_job_chain_sorted_by_time(client):
    body = client.get("/api/events", params={"job_id": "JOB-2003"}).json()
    assert body["total"] == 3
    assert [e["host"] for e in body["items"]] == [
        "mait_win03_cad_converter", "mait_linux1_teamcenter_app", "mait_linux1_teamcenter_app"]
    first = body["items"][0]
    assert first["ts_utc"] == "2026-11-24T08:30:00Z"
    assert first["source_path"].endswith("nx_jt/creative_2026-11-24.csv")
    assert (first["line_start"], first["is_duplicate"]) == (2, False)


def test_events_filters(client):
    errors = client.get("/api/events", params={"level": "error,fatal"}).json()
    assert errors["total"] == 3
    text = client.get("/api/events", params={"q": "write permission"}).json()
    assert text["total"] == 1 and text["items"][0]["job_id"] == "JOB-2003"
    window = client.get("/api/events", params={"from": "2026-11-24T09:29:00+01:00",
                                               "to": "2026-11-24T08:30:10Z"}).json()
    assert window["total"] == 3  # 08:29:22, 08:30:00, 08:30:08
    page = client.get("/api/events", params={"limit": 2, "offset": 2}).json()
    assert (page["total"], len(page["items"]), page["offset"]) == (6, 2, 2)
    assert client.get("/api/events", params={"level": "LOUD"}).status_code == 422


def test_event_detail_and_context(client):
    item = client.get("/api/events", params={"q": "write permission"}).json()["items"][0]
    detail = client.get(f"/api/events/{item['id']}").json()
    assert detail["format"] == "bracket_json" and detail["level_raw"] == "ERROR"
    assert detail["attrs"] == {} and detail["raw"].startswith("2026-11-24T08:30:08Z [ERROR]")

    ctx = client.get(f"/api/events/{item['id']}/context", params={"n": 1}).json()
    assert [(line["no"], line["is_event"]) for line in ctx["lines"]] == [
        (1, False), (2, True), (3, False)]
    assert ctx["encoding"] == "utf-8"


def test_context_for_multiline_and_gzip(client):
    exc = client.get("/api/events", params={"job_id": "JOB-2010"}).json()["items"][0]
    ctx = client.get(f"/api/events/{exc['id']}/context", params={"n": 0}).json()
    assert [line["no"] for line in ctx["lines"]] == [3, 4, 5]
    assert all(line["is_event"] for line in ctx["lines"])
    assert ctx["lines"][2]["text"].startswith("Caused by:")

    publish = client.get("/api/events", params={"q": "Publish task"}).json()["items"][0]
    ctx = client.get(f"/api/events/{publish['id']}/context").json()
    assert ctx["lines"][0]["text"].startswith('{"timestamp"')


def test_not_found(client):
    assert client.get("/api/events/999999").status_code == 404
    assert client.get("/api/events/999999/context").status_code == 404
