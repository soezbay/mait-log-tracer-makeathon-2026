import os
import zipfile

import pytest

from logtracer.core.logpaket import ensure_log_package

FILES = {
    "README.md": "readme",
    "mait_linux1/server_info.json": '{"os_family": "Linux"}',
    "mait_linux1/logs/os/network/2026-11-23.log": "line 1\nline 2\n",
    "mait_win01/logs/dispatcher/core/creative_2026-11-24.csv": "timestamp;level\n",
}


@pytest.fixture
def paths(tmp_path):
    zip_path = tmp_path / "MAIT_Makeathon_Logpaket.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("MAIT_Makeathon_Logpaket/", "")
        for name, content in FILES.items():
            z.writestr(f"MAIT_Makeathon_Logpaket/{name}", content)
    return zip_path, tmp_path / "MAIT_Makeathon_Logpaket", tmp_path / "data" / "marker.json"


def test_first_start_extracts_everything(paths):
    zip_path, root, marker = paths
    result = ensure_log_package(zip_path, root, marker)
    assert (result.action, result.files_extracted, result.files_total) == ("extracted", 4, 4)
    for name, content in FILES.items():
        assert (root / name).read_text() == content  # top-level folder stripped
    assert marker.is_file()


def test_second_start_is_a_fast_no_op(paths):
    zip_path, root, marker = paths
    ensure_log_package(zip_path, root, marker)
    result = ensure_log_package(zip_path, root, marker)
    assert (result.action, result.files_extracted) == ("present", 0)
    assert result.message == "already extracted"


def test_missing_files_are_restored_and_others_untouched(paths):
    zip_path, root, marker = paths
    ensure_log_package(zip_path, root, marker)
    log = root / "mait_linux1/logs/os/network/2026-11-23.log"
    before = log.stat().st_mtime_ns
    (root / "README.md").unlink()
    marker.unlink()
    result = ensure_log_package(zip_path, root, marker)
    assert (result.action, result.files_extracted) == ("repaired", 1)
    assert (root / "README.md").is_file()
    assert log.stat().st_mtime_ns == before  # existing file not rewritten


def test_new_zip_version_triggers_a_check(paths):
    zip_path, root, marker = paths
    ensure_log_package(zip_path, root, marker)
    with zipfile.ZipFile(zip_path, "a") as z:
        z.writestr("MAIT_Makeathon_Logpaket/mait_linux1/logs/os/network/new.log", "x\n")
    st = zip_path.stat()
    os.utime(zip_path, ns=(st.st_atime_ns, st.st_mtime_ns + 10_000_000_000))
    result = ensure_log_package(zip_path, root, marker)
    assert (result.action, result.files_extracted) == ("repaired", 1)


def test_lfs_pointer_gives_clear_message(tmp_path):
    zip_path = tmp_path / "MAIT_Makeathon_Logpaket.zip"
    zip_path.write_text("version https://git-lfs.github.com/spec/v1\noid sha256:abc\nsize 83440634\n")
    result = ensure_log_package(zip_path, tmp_path / "missing", tmp_path / "m.json")
    assert result.action == "lfs_pointer" and not result.ok
    assert "git lfs pull" in result.message


def test_missing_zip_but_existing_folder_is_fine(tmp_path):
    root = tmp_path / "pkg"
    (root / "srv").mkdir(parents=True)
    result = ensure_log_package(tmp_path / "nope.zip", root, tmp_path / "m.json")
    assert result.ok and result.action == "present"
    missing = ensure_log_package(tmp_path / "nope.zip", tmp_path / "empty", tmp_path / "m.json")
    assert missing.action == "missing_zip" and not missing.ok


def test_missing_zip_is_downloaded_then_extracted(paths, monkeypatch):
    zip_path, root, marker = paths
    content = zip_path.read_bytes()
    zip_path.write_text("version https://git-lfs.github.com/spec/v1\noid sha256:abc\n")
    calls = []

    def fake_download(path):
        calls.append(path)
        path.write_bytes(content)  # what `git lfs pull` does
        return True, "downloaded MAIT_Makeathon_Logpaket.zip (0 MB)"

    monkeypatch.setattr("logtracer.core.logpaket.download_zip", fake_download)
    result = ensure_log_package(zip_path, root, marker, download=True)
    assert calls == [zip_path]
    assert (result.action, result.files_extracted) == ("extracted", 4)
    assert result.message.startswith("downloaded")
    # next start: ZIP present, nothing downloaded again
    assert ensure_log_package(zip_path, root, marker, download=True).action == "present"
    assert len(calls) == 1


def test_failed_download_gives_clear_message(tmp_path, monkeypatch):
    monkeypatch.setattr("logtracer.core.logpaket.download_zip",
                        lambda path: (False, "git lfs pull failed: auth required"))
    result = ensure_log_package(tmp_path / "x.zip", tmp_path / "pkg", tmp_path / "m.json",
                                download=True)
    assert result.action == "missing_zip" and "auth required" in result.message


def test_unsafe_paths_are_rejected(tmp_path):
    zip_path = tmp_path / "evil.zip"
    with zipfile.ZipFile(zip_path, "w") as z:
        z.writestr("../outside.txt", "nope")
    with pytest.raises(ValueError, match="unsafe path"):
        ensure_log_package(zip_path, tmp_path / "pkg", tmp_path / "m.json")
    assert not (tmp_path / "outside.txt").exists()
