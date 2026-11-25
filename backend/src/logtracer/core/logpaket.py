"""Make sure the MAIT log package is downloaded and extracted before anything reads it.

The package is versioned as one ZIP via Git LFS (`MAIT_Makeathon_Logpaket.zip` at the repo
root). On program start the backend (API server, scripts/ingest.py, scripts/make_fixture.py)
calls `ensure_log_package`:

- ZIP missing or only a Git LFS pointer      -> download it once with `git lfs pull`
                                               (same Git login as for push; works for a
                                               private repo)
- marker unchanged (same ZIP size and mtime) -> nothing to do (fast path, no disk scan)
- folder missing or incomplete                -> extract the missing files once

Existing files with the right size are never rewritten. The marker lives next to the
database (data/), not inside the log package, so the package folder stays untouched.
"""

import json
import logging
import subprocess
import time
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

log = logging.getLogger("logtracer.logpaket")

LFS_POINTER_PREFIX = b"version https://git-lfs"


@dataclass
class ExtractResult:
    action: str  # present | extracted | repaired | missing_zip | lfs_pointer
    files_extracted: int = 0
    files_total: int = 0
    elapsed_s: float = 0.0
    message: str = ""

    @property
    def ok(self) -> bool:
        return self.action in ("present", "extracted", "repaired")


def _is_lfs_pointer(zip_path: Path) -> bool:
    if zip_path.stat().st_size > 1024:
        return False
    return zip_path.read_bytes().startswith(LFS_POINTER_PREFIX)


def _needs_download(zip_path: Path) -> bool:
    return not zip_path.is_file() or _is_lfs_pointer(zip_path)


def _has_content(folder: Path) -> bool:
    return folder.is_dir() and any(folder.iterdir())


def _zip_signature(zip_path: Path) -> dict:
    stat = zip_path.stat()
    return {"zip": zip_path.name, "size": stat.st_size, "mtime_ns": stat.st_mtime_ns}


def _check_entry(name: str) -> None:
    """Reject absolute paths, drive letters and '..' (zip slip) before anything is written."""
    normalized = name.replace("\\", "/")
    parts = PurePosixPath(normalized).parts
    if not parts or normalized.startswith("/") or ".." in parts or ":" in parts[0]:
        raise ValueError(f"unsafe path in ZIP: {name!r}")


def _strip_prefix(names: list[str]) -> str | None:
    """Common top-level folder of all entries (e.g. 'MAIT_Makeathon_Logpaket'), if any."""
    tops = {PurePosixPath(n).parts[0] for n in names if n.strip("/")}
    if len(tops) == 1:
        top = tops.pop()
        if all(n == f"{top}/" or n.startswith(f"{top}/") for n in names):
            return top
    return None


def download_zip(zip_path: Path, timeout_s: int = 900) -> tuple[bool, str]:
    """Fetch the ZIP from Git LFS (`git lfs pull --include <zip>`). Returns (ok, message)."""
    zip_path = Path(zip_path)
    try:
        top = subprocess.run(["git", "rev-parse", "--show-toplevel"], cwd=zip_path.parent,
                             capture_output=True, text=True, timeout=30, check=True)
        repo_root = Path(top.stdout.strip())
        relative = zip_path.resolve().relative_to(repo_root.resolve()).as_posix()
        subprocess.run(["git", "lfs", "pull", "--include", relative], cwd=repo_root,
                       capture_output=True, text=True, timeout=timeout_s, check=True)
    except FileNotFoundError:
        return False, "git is not installed or not on PATH"
    except subprocess.CalledProcessError as exc:
        lines = (exc.stderr or exc.stdout or str(exc)).strip().splitlines()
        return False, f"git lfs pull failed: {lines[-1] if lines else exc}"
    except (subprocess.TimeoutExpired, ValueError, OSError) as exc:
        return False, f"download failed: {exc}"
    if _needs_download(zip_path):
        return False, "git lfs pull finished but the ZIP is still missing or only a pointer"
    return True, f"downloaded {zip_path.name} ({zip_path.stat().st_size / 1e6:.0f} MB)"


def ensure_log_package(zip_path: Path, log_root: Path, marker_path: Path,
                       download: bool = False) -> ExtractResult:
    started = time.perf_counter()
    zip_path, log_root, marker_path = Path(zip_path), Path(log_root), Path(marker_path)

    note = ""
    if download and _needs_download(zip_path):
        ok, note = download_zip(zip_path)
        log.log(logging.INFO if ok else logging.WARNING, "log package download: %s", note)

    if not zip_path.is_file():
        if _has_content(log_root):
            return ExtractResult("present", message="no ZIP found, using the existing folder")
        return ExtractResult("missing_zip", message=(
            f"Log package missing: neither {log_root} nor {zip_path} exists. "
            f"Run `git lfs pull` in the repo root. {note}".strip()))

    if _is_lfs_pointer(zip_path):
        if _has_content(log_root):
            return ExtractResult("present", message="ZIP is an LFS pointer, using existing folder")
        return ExtractResult("lfs_pointer", message=(
            f"{zip_path.name} is only a Git LFS pointer. Run `git lfs install` and "
            f"`git lfs pull` in the repo root, then start again. {note}".strip()))

    signature = _zip_signature(zip_path)
    try:
        marker = json.loads(marker_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        marker = None
    if marker and marker.get("signature") == signature and _has_content(log_root):
        return ExtractResult("present", files_total=marker.get("files", 0),
                             message="already extracted")

    existed = _has_content(log_root)
    extracted = 0
    with zipfile.ZipFile(zip_path) as archive:
        infos = archive.infolist()
        for info in infos:
            _check_entry(info.filename)
        entries = [i for i in infos if not i.is_dir()]
        prefix = _strip_prefix([i.filename for i in infos])
        for info in entries:
            relative = info.filename[len(prefix) + 1:] if prefix else info.filename
            target = log_root.joinpath(*PurePosixPath(relative).parts)
            if target.is_file() and target.stat().st_size == info.file_size:
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(info) as src, open(target, "wb") as dst:
                while chunk := src.read(1 << 20):
                    dst.write(chunk)
            extracted += 1

    marker_path.parent.mkdir(parents=True, exist_ok=True)
    marker_path.write_text(json.dumps({"signature": signature, "files": len(entries),
                                       "log_root": str(log_root)}, indent=2), encoding="utf-8")
    if extracted == 0:
        action = "present"
    else:
        action = "repaired" if existed else "extracted"
    message = f"{extracted} of {len(entries)} files extracted"
    return ExtractResult(action, files_extracted=extracted, files_total=len(entries),
                         elapsed_s=round(time.perf_counter() - started, 2),
                         message=f"{note}; {message}" if note else message)


def ensure_from_settings(settings) -> ExtractResult:
    """Run the check with the configured paths and log the outcome."""
    if not settings.auto_extract:
        return ExtractResult("present", message="AUTO_EXTRACT is off")
    result = ensure_log_package(settings.logpaket_zip, settings.log_root,
                                settings.db_path.parent / "logpaket.extracted.json",
                                download=settings.auto_download)
    level = logging.INFO if result.ok else logging.ERROR
    log.log(level, "log package: %s (%s, %.1f s)", result.action, result.message,
            result.elapsed_s)
    return result
