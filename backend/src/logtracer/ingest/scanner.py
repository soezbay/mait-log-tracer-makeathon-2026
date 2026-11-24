"""Find all log files below LOG_ROOT.

Layout: <server>/logs/<application>/<component...>/<file>. The component can have more than
one level (e.g. dispatcher/translators/nx_jt). README.md and server_info.json are metadata,
not logs. Folders starting with "_" or "." (e.g. _dokumentation) are not servers.
"""

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

METADATA_FILES = {"README.md", "server_info.json"}


@dataclass(frozen=True)
class ServerInfo:
    server: str
    os: str | None
    role: str | None
    info: dict = field(default_factory=dict)


@dataclass(frozen=True)
class ScannedFile:
    path: str  # relative to LOG_ROOT, forward slashes
    abs_path: Path
    server: str
    application: str | None
    component: str | None
    compressed: bool
    size: int
    mtime: datetime  # UTC, naive


def read_server_info(server_dir: Path) -> ServerInfo:
    info_file = server_dir / "server_info.json"
    if not info_file.is_file():
        return ServerInfo(server=server_dir.name, os=None, role=None)
    info = json.loads(info_file.read_text(encoding="utf-8"))
    return ServerInfo(
        server=server_dir.name,
        os=info.get("os_family"),
        role=info.get("role"),
        info=info,
    )


def _server_dirs(log_root: Path) -> list[Path]:
    return sorted(
        p for p in log_root.iterdir()
        if p.is_dir() and not p.name.startswith(("_", ".")) and (p / "logs").is_dir()
    )


def scan(log_root: Path) -> tuple[list[ServerInfo], list[ScannedFile]]:
    """Return all servers and all log files, sorted by path (stable source IDs)."""
    log_root = Path(log_root)
    servers: list[ServerInfo] = []
    files: list[ScannedFile] = []

    for server_dir in _server_dirs(log_root):
        servers.append(read_server_info(server_dir))
        logs_dir = server_dir / "logs"
        for file in sorted(logs_dir.rglob("*")):
            if not file.is_file() or file.name in METADATA_FILES:
                continue
            parts = file.relative_to(logs_dir).parts  # application, component..., file name
            stat = file.stat()
            files.append(
                ScannedFile(
                    path=file.relative_to(log_root).as_posix(),
                    abs_path=file,
                    server=server_dir.name,
                    application=parts[0] if len(parts) > 1 else None,
                    component="/".join(parts[1:-1]) or None,
                    compressed=file.suffix == ".gz",
                    size=stat.st_size,
                    mtime=datetime.fromtimestamp(stat.st_mtime, UTC).replace(tzinfo=None),
                )
            )
    return servers, files
