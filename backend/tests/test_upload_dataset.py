"""Uploaded ZIP as the active data set: POST /api/ingest/upload, /ingest/original, /ingest/dataset."""

import io
import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from logtracer.core.config import Settings
from logtracer.main import create_app
from logtracer.services import dataset_service

ORIGINAL_LINE = (
    "2026-11-24T08:00:00Z [INFO] host=mait_linux1_teamcenter_app component=fms/fsc "
    'event_id=E-1 job_id=OK-1 | {"message": "Dataset transferred"}\n'
)
UPLOAD_LINES = "".join(
    f"2026-11-24T09:00:0{i}Z [ERROR] host=mait_win09_test component=nx/batch "
    f'event_id=U-{i} job_id=JOB-9{i} | {{"message": "Uploaded failure {i}"}}\n'
    for i in range(3)
)


def _settings(tmp_path: Path, root: Path) -> Settings:
    return Settings(_env_file=None, log_root=root, db_path=tmp_path / "data" / "t.duckdb",
                    auto_extract=False, auto_download=False, watch_enabled=False)


def _zip(entries: dict[str, str | bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for name, data in entries.items():
            z.writestr(name, data)
    return buf.getvalue()


@pytest.fixture
def original_root(tmp_path):
    root = tmp_path / "original"
    comp = root / "mait_linux1_teamcenter_app" / "logs" / "fms" / "fsc"
    comp.mkdir(parents=True)
    (comp / "creative_2026-11-24.txt").write_text(ORIGINAL_LINE, encoding="utf-8")
    return root


def _ingest_original(client) -> None:
    assert client.post("/api/ingest", json={"mode": "full"}).status_code == 202
    client.app.state.ingest.wait(timeout=30)


def _upload(client, data: bytes, name="pack.zip"):
    r = client.post(f"/api/ingest/upload?name={name}", content=data,
                    headers={"Content-Type": "application/zip"})
    client.app.state.ingest.wait(timeout=30)
    return r


PACK = {
    # wrapper folders, like an unzipped and re-zipped package
    "pack/inner/mait_win09_test/logs/nx/batch/creative_2026-11-24.txt": UPLOAD_LINES,
    "pack/inner/mait_win09_test/server_info.json": '{"os_family": "Windows"}',
    "pack/README.md": "ignored",
    "pack/inner/picture.png": b"\x89PNG",
    "../evil.log": "must never be written",
    "pack/__MACOSX/._x.log": "junk",
}


def test_upload_becomes_the_active_dataset_and_survives_a_restart(tmp_path, original_root):
    settings = _settings(tmp_path, original_root)
    with TestClient(create_app(settings)) as c:
        _ingest_original(c)
        assert c.get("/api/stats").json()["events"] == 1
        assert c.get("/api/ingest/dataset").json()["dataset"]["kind"] == "original"

        r = _upload(c, _zip(PACK))
        assert r.status_code == 202, r.text
        state = c.get("/api/ingest/dataset").json()
        assert state["dataset"] == {**state["dataset"], "kind": "upload", "name": "pack.zip",
                                    "files": 2}
        assert state["running"] is False and state["error"] is None
        stats = c.get("/api/stats").json()
        assert stats["events"] == 3 and stats["levels"]["ERROR"] == 3
        # source lines are read from the uploaded files
        event = c.get("/api/events?job_id=JOB-91").json()["items"][0]
        context = c.get(f"/api/events/{event['id']}/context?n=1").json()
        assert any("Uploaded failure 1" in line["text"] for line in context["lines"])
        # the analysis ran on the upload
        assert c.get("/api/analysis/status").json()["counts"]["events"] == 3

    # nothing escaped the upload folder, the original package is untouched
    assert not (tmp_path / "data" / "evil.log").exists()
    assert not any(p.name == "evil.log" for p in tmp_path.rglob("*"))
    assert [p.name for p in original_root.rglob("*.txt")] == ["creative_2026-11-24.txt"]
    assert dataset_service.marker_path(settings).is_file()

    with TestClient(create_app(settings)) as c:  # restart: still the upload
        assert c.get("/api/ingest/dataset").json()["dataset"]["kind"] == "upload"
        assert c.get("/api/stats").json()["events"] == 3

        assert c.post("/api/ingest/original").status_code == 202
        c.app.state.ingest.wait(timeout=30)
        assert c.get("/api/ingest/dataset").json()["dataset"]["kind"] == "original"
        assert c.get("/api/stats").json()["events"] == 1
    assert not dataset_service.marker_path(settings).exists()


def test_rejected_uploads_leave_the_data_alone(tmp_path, original_root, monkeypatch):
    with TestClient(create_app(_settings(tmp_path, original_root))) as c:
        _ingest_original(c)
        not_zip = _upload(c, b"definitely not a zip")
        assert not_zip.status_code == 400 and "not a readable ZIP" in not_zip.json()["detail"]
        no_logs = _upload(c, _zip({"notes/readme.md": "hi", "a.txt": "loose file"}))
        assert no_logs.status_code == 400 and "No log folders" in no_logs.json()["detail"]
        assert _upload(c, b"").status_code == 400
        monkeypatch.setattr(dataset_service, "MAX_UPLOAD_BYTES", 100)
        too_big = _upload(c, _zip(PACK))
        assert too_big.status_code == 413
        # still the original data, no upload folders left behind
        assert c.get("/api/stats").json()["events"] == 1
        assert c.get("/api/ingest/dataset").json()["dataset"]["kind"] == "original"
        assert not any(dataset_service.uploads_dir(c.app.state.settings).iterdir())


def test_upload_is_refused_while_an_ingest_runs(tmp_path, original_root):
    with TestClient(create_app(_settings(tmp_path, original_root))) as c:
        c.app.state.ingest.state["running"] = True
        try:
            assert _upload(c, _zip(PACK)).status_code == 409
            assert c.post("/api/ingest/original").status_code == 409
        finally:
            c.app.state.ingest.state["running"] = False


def test_watcher_changes_are_ignored_while_an_upload_is_active(tmp_path, original_root):
    with TestClient(create_app(_settings(tmp_path, original_root))) as c:
        _ingest_original(c)
        assert _upload(c, _zip(PACK)).status_code == 202
        manager = c.app.state.ingest
        manager.on_files_changed([original_root / "x" / "logs" / "a" / "b.txt"])
        assert manager.state["running"] is False and c.get("/api/stats").json()["events"] == 3


def test_extract_limits_and_root_detection(tmp_path, monkeypatch):
    zip_path = tmp_path / "p.zip"
    zip_path.write_bytes(_zip(PACK))
    root, files, skipped = dataset_service.extract_upload(zip_path, tmp_path / "out")
    assert root == (tmp_path / "out" / "pack" / "inner").resolve()
    assert files == 2 and skipped == 4  # README, png, ../evil.log, __MACOSX
    monkeypatch.setattr(dataset_service, "MAX_EXTRACTED_BYTES", 50)
    with pytest.raises(dataset_service.UploadError) as err:
        dataset_service.extract_upload(zip_path, tmp_path / "out2")
    assert err.value.status == 413
