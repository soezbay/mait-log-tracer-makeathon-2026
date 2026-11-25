"""Watch the log folder and report changed files after a quiet period (debounce).

Uses watchdog (ReadDirectoryChangesW on Windows, inotify on Linux). Several events for the same
file (create + modify + modify …) are collected and handed over once, after `debounce_s`
seconds without further changes.
"""

import threading
from collections.abc import Callable
from pathlib import Path

from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

from logtracer.ingest.scanner import METADATA_FILES

ChangeHandler = Callable[[list[Path]], None]


class LogWatcher(FileSystemEventHandler):
    def __init__(self, log_root: Path, on_changes: ChangeHandler, debounce_s: float = 1.5) -> None:
        self.log_root = Path(log_root)
        self.on_changes = on_changes
        self.debounce_s = debounce_s
        self._pending: set[Path] = set()
        self._lock = threading.Lock()
        self._timer: threading.Timer | None = None
        self._observer = None

    # watchdog callback (runs in the observer thread)
    def on_any_event(self, event: FileSystemEvent) -> None:
        if event.is_directory or event.event_type not in ("created", "modified", "moved", "closed"):
            return
        path = Path(getattr(event, "dest_path", "") or event.src_path)
        if path.name in METADATA_FILES or path.name.startswith(("~", ".")):
            return
        with self._lock:
            self._pending.add(path)
            if self._timer is not None:
                self._timer.cancel()
            self._timer = threading.Timer(self.debounce_s, self._flush)
            self._timer.daemon = True
            self._timer.start()

    def _flush(self) -> None:
        with self._lock:
            paths, self._pending, self._timer = sorted(self._pending), set(), None
        if paths:
            self.on_changes(paths)

    def start(self) -> None:
        # Short emitter timeout: watchdog's default (1 s per read) adds noticeable latency.
        self._observer = Observer(timeout=0.2)
        self._observer.schedule(self, str(self.log_root), recursive=True)
        self._observer.daemon = True
        self._observer.start()

    def stop(self) -> None:
        with self._lock:
            if self._timer is not None:
                self._timer.cancel()
        if self._observer is not None:
            self._observer.stop()
            self._observer.join(timeout=5)
            self._observer = None
