"""Uploaded log packages as the active data set ("Analyze on server" in the frontend).

The app analyses one log folder at a time: the original package (`LOG_ROOT`) or a ZIP that was
uploaded through `POST /api/ingest/upload`. An upload is extracted below `data/uploads/`, never
into the original package, and then ingested with the normal full ingest + analysis, so every
page, the incidents and the assistant work on it unchanged. A small JSON marker next to the
database remembers the active data set across restarts.

Extraction is defensive: size and file-count limits, only log files and `server_info.json`, and
no entry may leave its target folder (absolute paths, `..`, drive letters are skipped).
"""

from __future__ import annotations

import json
import re
import shutil
import tempfile
import zipfile
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any

from logtracer.core.config import Settings

MAX_UPLOAD_BYTES = 256 * 1024 * 1024        # the ZIP itself
MAX_EXTRACTED_BYTES = 2 * 1024 * 1024 * 1024  # all extracted files (the full package is ~0.9 GB)
MAX_FILES = 50_000
KEEP_UPLOADS = 3                             # older upload folders are deleted
LOG_FILE = re.compile(r"\.(?:log|txt|csv|jsonl|xml)(?:\.gz)?$", re.IGNORECASE)
_SAFE_NAME = re.compile(r"[^A-Za-z0-9._-]+")


class UploadError(Exception):
    """A rejected upload; `status` is the HTTP status the API answers with."""

    def __init__(self, message: str, status: int = 400) -> None:
        super().__init__(message)
        self.status = status


def _now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _data_dir(settings: Settings) -> Path:
    if str(settings.db_path) == ":memory:":
        return Path(tempfile.gettempdir()) / "logtracer"
    return Path(settings.db_path).parent


def marker_path(settings: Settings) -> Path | None:
    """`<db name>.dataset.json` next to the database (None for an in-memory database)."""
    if str(settings.db_path) == ":memory:":
        return None
    db = Path(settings.db_path)
    return db.with_name(f"{db.stem}.dataset.json")


def uploads_dir(settings: Settings) -> Path:
    return _data_dir(settings) / "uploads"


def original_dataset(settings: Settings) -> dict[str, Any]:
    return {"kind": "original", "name": Path(settings.log_root).name,
            "log_root": str(settings.log_root), "activated_at": None, "files": None}


def load_active(settings: Settings) -> dict[str, Any] | None:
    """The uploaded data set the database holds, or None for the original package."""
    path = marker_path(settings)
    if path is None or not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if data.get("kind") != "upload" or not Path(data.get("log_root", "")).is_dir():
        return None
    return data


def save_active(settings: Settings, dataset: dict[str, Any]) -> None:
    path = marker_path(settings)
    if path is None:
        return
    if dataset.get("kind") == "upload":
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(dataset, indent=2), encoding="utf-8")
    else:
        path.unlink(missing_ok=True)


def new_upload_dir(settings: Settings, filename: str) -> Path:
    stem = _SAFE_NAME.sub("_", Path(filename or "upload.zip").stem)[:60] or "upload"
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%f")
    path = uploads_dir(settings) / f"{stamp}-{stem}"
    path.mkdir(parents=True, exist_ok=False)
    return path


def safe_name(filename: str) -> str:
    name = Path(filename or "upload.zip").name
    return _SAFE_NAME.sub("_", name)[:120] or "upload.zip"


def _member_parts(name: str) -> tuple[str, ...] | None:
    """Path parts of a ZIP entry, or None if the entry must not be extracted."""
    name = name.replace("\\", "/")
    parts = PurePosixPath(name).parts
    if (not parts or name.startswith("/") or ".." in parts or ":" in parts[0]
            or "__MACOSX" in parts or any(p.startswith(".") for p in parts)):
        return None
    return parts


def extract_upload(zip_path: Path, dest: Path) -> tuple[Path, int, int]:
    """Extract the log files of a ZIP into `dest`.

    Returns (log root inside dest, files extracted, entries skipped). The log root is the folder
    that holds the server folders (`<server>/logs/...`), however deep the ZIP nests it.
    """
    try:
        archive = zipfile.ZipFile(zip_path)
    except (zipfile.BadZipFile, OSError) as exc:
        raise UploadError("The file is not a readable ZIP archive.") from exc
    dest = Path(dest).resolve()
    dest.mkdir(parents=True, exist_ok=True)
    total = extracted = skipped = 0
    with archive:
        for info in archive.infolist():
            if info.is_dir():
                continue
            parts = _member_parts(info.filename)
            if parts is None or not (LOG_FILE.search(parts[-1]) or parts[-1] == "server_info.json"):
                skipped += 1
                continue
            extracted += 1
            if extracted > MAX_FILES:
                raise UploadError(f"More than {MAX_FILES} log files in the ZIP.", 413)
            target = dest.joinpath(*parts).resolve()
            if not target.is_relative_to(dest):  # defence in depth against path tricks
                skipped += 1
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(info) as src, open(target, "wb") as out:
                while chunk := src.read(1024 * 1024):
                    total += len(chunk)
                    if total > MAX_EXTRACTED_BYTES:
                        raise UploadError(
                            f"The extracted logs exceed {MAX_EXTRACTED_BYTES // 2**20} MiB.", 413)
                    out.write(chunk)
    root = find_log_root(dest)
    if root is None:
        raise UploadError(
            "No log folders found. Expected <server>/logs/<application>/... inside the ZIP, "
            "like the MAIT log package.")
    return root, extracted, skipped


def find_log_root(base: Path, max_depth: int = 4) -> Path | None:
    """The shallowest folder whose subfolders contain `logs/` (the server folders)."""
    level = [Path(base)]
    for _ in range(max_depth + 1):
        for folder in sorted(level):
            if any(child.is_dir() and (child / "logs").is_dir() for child in folder.iterdir()):
                return folder
        level = [child for folder in level for child in folder.iterdir() if child.is_dir()]
        if not level:
            return None
    return None


def prune_uploads(settings: Settings, keep: Path) -> None:
    """Delete old upload folders, keeping the newest few and the active one."""
    folder = uploads_dir(settings)
    if not folder.is_dir():
        return
    keep = keep.resolve()
    entries = sorted((p for p in folder.iterdir() if p.is_dir()), reverse=True)
    for old in entries[KEEP_UPLOADS:]:
        if not keep.is_relative_to(old.resolve()):
            shutil.rmtree(old, ignore_errors=True)


def upload_dataset(name: str, root: Path, files: int) -> dict[str, Any]:
    return {"kind": "upload", "name": name, "log_root": str(root), "activated_at": _now_iso(),
            "files": files}
