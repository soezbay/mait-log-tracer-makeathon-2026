import gzip
import json

import pytest

from logtracer.ingest.fingerprint import DuplicateIndex, sha256
from logtracer.ingest.pipeline import scan_sources
from logtracer.ingest.reader import decode, read_bytes, split_lines
from logtracer.ingest.scanner import scan
from logtracer.storage.db import connect, init_schema

# Real line shapes from the log package.
KV_LINE = (
    "2026-11-23T08:00:14Z WARN host=mait_linux1 component=os/network event_id=E-00003600 "
    "job_id=NORMAL-03444 | Transient latency; retry succeeded\r\n"
)
JSONL_LINE = json.dumps({"timestamp": "2026-11-24T08:30:12Z", "level": "ERROR",
                         "message": "Publish task failed"}) + "\n"


@pytest.fixture
def log_root(tmp_path):
    """Small copy of the log package layout."""
    linux = tmp_path / "mait_linux1"
    (linux / "logs" / "os" / "network").mkdir(parents=True)
    (linux / "server_info.json").write_text(
        json.dumps({"hostname": "mait_linux1", "os_family": "Linux", "role": "Teamcenter Backend"}),
        encoding="utf-8",
    )
    net = linux / "logs" / "os" / "network"
    (net / "README.md").write_text("# metadata", encoding="utf-8")
    (net / "2026-11-23.log").write_bytes((KV_LINE * 3).encode())
    (net / "2026-11-23_run01.log").write_bytes((KV_LINE * 3).encode())  # byte-identical copy

    win = tmp_path / "mait_windows1"
    trans = win / "logs" / "dispatcher" / "translators" / "nx_jt"
    trans.mkdir(parents=True)
    (win / "server_info.json").write_text(
        json.dumps({"hostname": "mait_windows1", "os_family": "Windows",
                    "synthetic_demo_role": True}),
        encoding="utf-8",
    )
    (trans / "2026-11-24.jsonl").write_bytes(JSONL_LINE.encode())
    (trans / "2026-11-24.jsonl.gz").write_bytes(gzip.compress(JSONL_LINE.encode()))  # same content
    (trans / "creative.txt").write_bytes("Größe überschritten\r\n".encode("cp1252"))

    (tmp_path / "_dokumentation").mkdir()
    (tmp_path / "_dokumentation" / "QUELLEN.md").write_text("docs", encoding="utf-8")
    (tmp_path / "README.md").write_text("root readme", encoding="utf-8")
    return tmp_path


def test_scan_finds_only_log_files(log_root):
    servers, files = scan(log_root)
    assert [s.server for s in servers] == ["mait_linux1", "mait_windows1"]
    assert servers[0].os == "Linux" and servers[0].role == "Teamcenter Backend"
    assert servers[1].role is None  # some servers have no role
    paths = [f.path for f in files]
    assert len(paths) == 5
    assert not any(p.endswith(("README.md", "server_info.json", "QUELLEN.md")) for p in paths)


def test_scan_derives_application_and_multi_level_component(log_root):
    _, files = scan(log_root)
    by_name = {f.path.rsplit("/", 1)[1]: f for f in files}
    assert by_name["2026-11-23.log"].application == "os"
    assert by_name["2026-11-23.log"].component == "network"
    assert by_name["creative.txt"].application == "dispatcher"
    assert by_name["creative.txt"].component == "translators/nx_jt"
    assert by_name["2026-11-24.jsonl.gz"].compressed is True


def test_reader_decompresses_and_detects_encoding(log_root):
    trans = log_root / "mait_windows1" / "logs" / "dispatcher" / "translators" / "nx_jt"
    assert read_bytes(trans / "2026-11-24.jsonl.gz") == read_bytes(trans / "2026-11-24.jsonl")
    text, encoding = decode(read_bytes(trans / "creative.txt"))
    assert encoding == "cp1252"
    assert text.startswith("Größe")
    assert decode("Größe".encode()) == ("Größe", "utf-8")
    assert decode(b"\xef\xbb\xbfabc") == ("abc", "utf-8-sig")


def test_split_lines_handles_crlf_and_trailing_newline():
    assert split_lines("a\r\nb\r\n") == ["a", "b"]
    assert split_lines("a\nb") == ["a", "b"]
    assert split_lines("a b\n") == ["a b"]  # only \n splits
    assert split_lines("") == []


def test_duplicate_index():
    index = DuplicateIndex()
    digest = sha256(b"x")
    assert index.add(digest, 1) is None
    assert index.add(digest, 2) == 1
    assert len(index) == 1


def test_scan_sources_writes_servers_and_sources(log_root):
    con = connect(":memory:")
    init_schema(con)
    result = scan_sources(con, log_root)
    assert result.errors == []

    assert con.execute("SELECT count(*) FROM servers").fetchone()[0] == 2
    rows = con.execute(
        "SELECT path, duplicate_of, encoding FROM sources ORDER BY source_id"
    ).fetchall()
    assert len(rows) == 5
    dupes = {path.rsplit("/", 1)[1]: dup for path, dup, _ in rows if dup is not None}
    # _run01 copy and the .gz with identical content are duplicates
    assert set(dupes) == {"2026-11-23_run01.log", "2026-11-24.jsonl.gz"}
    encodings = {path.rsplit("/", 1)[1]: enc for path, _, enc in rows}
    assert encodings["creative.txt"] == "cp1252"
    assert encodings["2026-11-23_run01.log"] == "utf-8"  # inherited from the original

    # Running the scan again replaces instead of duplicating.
    scan_sources(con, log_root)
    assert con.execute("SELECT count(*) FROM sources").fetchone()[0] == 5
