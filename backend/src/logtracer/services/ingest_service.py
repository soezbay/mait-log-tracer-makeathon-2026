"""Runs ingests in a background thread and streams their progress to SSE subscribers.

Only one ingest runs at a time. Changes reported by the watcher while an ingest runs are
queued and processed right after it. All writes go through a cursor of the app's single
DuckDB connection (DuckDB allows only one writing process). After an ingest that changed
something the analysis (P2) runs in the same thread, so the two never write at the same time.
"""

import asyncio
import logging
import threading
import time
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import duckdb

from logtracer.analysis import pipeline
from logtracer.core.config import Settings
from logtracer.ingest.full_ingest import full_ingest
from logtracer.ingest.incremental import incremental_ingest
from logtracer.services import dataset_service

log = logging.getLogger("logtracer.ingest")

MODES = ("full", "incremental")


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


class IngestManager:
    def __init__(self, con: duckdb.DuckDBPyConnection, settings: Settings) -> None:
        self.con = con
        self.settings = settings
        # Active data set: the original package or an uploaded ZIP (see dataset_service).
        self.log_root: Path = Path(settings.log_root)
        self.dataset: dict[str, Any] = dataset_service.original_dataset(settings)
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._queued_paths: set[Path] = set()
        self._subscribers: set[tuple[asyncio.AbstractEventLoop, asyncio.Queue]] = set()
        self._rescan_stop = threading.Event()
        self._rescan_thread: threading.Thread | None = None
        self.state: dict[str, Any] = {
            "running": False, "mode": None, "started_at": None, "finished_at": None,
            "last_result": None, "error": None,
        }
        self.analysis: dict[str, Any] = {
            "running": False, "started_at": None, "finished_at": None, "elapsed_s": None,
            "counts": None, "error": None,
        }

    # --- subscribers (SSE) -----------------------------------------------------------------

    def subscribe(self) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue(maxsize=1000)
        self._subscribers.add((asyncio.get_running_loop(), queue))
        return queue

    def unsubscribe(self, queue: asyncio.Queue) -> None:
        self._subscribers = {(loop, q) for loop, q in self._subscribers if q is not queue}

    def publish(self, event: str, data: dict) -> None:
        for loop, queue in list(self._subscribers):
            try:
                loop.call_soon_threadsafe(queue.put_nowait, (event, data))
            except RuntimeError:  # loop closed
                self._subscribers.discard((loop, queue))

    # --- starting ingests --------------------------------------------------------------------

    def start(self, mode: str, paths: Iterable[Path] | None = None, quiet: bool = False) -> bool:
        """Start an ingest in the background. Returns False if one is already running.

        quiet=True (periodic rescan): no events and no state change unless files changed.
        """
        if mode not in MODES:
            raise ValueError(f"mode must be one of {MODES}")
        with self._lock:
            return self._start_locked(mode, paths, quiet)

    def _start_locked(self, mode: str, paths: Iterable[Path] | None, quiet: bool = False) -> bool:
        if self.state["running"]:
            return False
        previous = dict(self.state)
        self.state.update(running=True, mode=mode, started_at=_now(), finished_at=None,
                          error=None)
        self._thread = threading.Thread(
            target=self._run,
            args=(mode, list(paths) if paths is not None else None, previous if quiet else None),
            name=f"ingest-{mode}", daemon=True,
        )
        self._thread.start()
        return True

    def start_analysis(self, only_if_needed: bool = False) -> bool:
        """Run only the analysis in the background. False if busy or not needed."""
        with self._lock:
            if self.state["running"]:
                return False
            if only_if_needed:
                cursor = self.con.cursor()
                try:
                    if not pipeline.is_needed(cursor):
                        return False
                finally:
                    cursor.close()
            self.state["running"] = True
            self._thread = threading.Thread(target=self._run_analysis, name="analysis",
                                            daemon=True)
            self._thread.start()
            return True

    # --- data set (original package or uploaded ZIP) ---------------------------------------

    def restore_dataset(self, dataset: dict[str, Any]) -> None:
        """On start-up: the database already holds this data set, only point the reads at it."""
        self.log_root = Path(dataset["log_root"])
        self.dataset = dataset

    def switch_dataset(self, dataset: dict[str, Any]) -> bool:
        """Make `dataset` active and rebuild the database from it (full ingest + analysis).

        Returns False if an ingest is running. The watcher and the periodic rescan only follow
        the original package, so they pause while an upload is active.
        """
        with self._lock:
            if self.state["running"]:
                return False
            self.log_root = Path(dataset["log_root"])
            self.dataset = dataset
            dataset_service.save_active(self.settings, dataset)
            return self._start_locked("full", None)

    @property
    def follows_original(self) -> bool:
        return self.dataset.get("kind") == "original"

    def on_files_changed(self, paths: list[Path]) -> None:
        """Watcher callback: ingest the changed files now, or right after the running ingest."""
        if not self.follows_original:  # the watcher watches the original package only
            return
        with self._lock:
            if not self._start_locked("incremental", paths, quiet=True):
                self._queued_paths.update(paths)

    def start_rescans(self, interval_s: float) -> None:
        """Safety net next to the watcher: check the whole package every `interval_s` seconds.

        File-change notifications on Windows can be delayed or lost; the rescan compares size
        and mtime of all files and only reports something when a file actually changed.
        """
        if interval_s <= 0 or self._rescan_thread is not None:
            return
        self._rescan_stop.clear()

        def loop() -> None:
            while not self._rescan_stop.wait(interval_s):
                if self.follows_original:
                    self.start("incremental", None, quiet=True)

        self._rescan_thread = threading.Thread(target=loop, name="ingest-rescan", daemon=True)
        self._rescan_thread.start()

    def stop_rescans(self) -> None:
        self._rescan_stop.set()
        if self._rescan_thread is not None:
            self._rescan_thread.join(timeout=5)
            self._rescan_thread = None

    def wait(self, timeout: float | None = None) -> None:
        """Block until no ingest runs (used by tests and scripts)."""
        deadline = None if timeout is None else time.monotonic() + timeout
        while True:
            thread = self._thread
            if (thread is None or not thread.is_alive()) and not self.state["running"]:
                return
            remaining = None if deadline is None else deadline - time.monotonic()
            if remaining is not None and remaining <= 0:
                return
            if thread is not None:
                thread.join(timeout=0.05 if remaining is None else min(0.05, remaining))

    # --- worker thread -----------------------------------------------------------------------

    def _run(self, mode: str, paths: list[Path] | None, quiet_previous: dict | None = None) -> None:
        quiet = quiet_previous is not None
        silent = False  # True when a quiet rescan found no changes
        cursor = self.con.cursor()
        started = time.perf_counter()
        if not quiet:
            self.publish("started", {"mode": mode,
                                     "files": len(paths) if paths is not None else None})
        try:
            if mode == "full":
                def progress(done: int, total: int, events: int) -> None:
                    self.publish("progress", {
                        "mode": mode, "files_done": done, "files_total": total,
                        "events_written": events,
                        "elapsed_s": round(time.perf_counter() - started, 1),
                    })

                res = full_ingest(cursor, self.log_root,
                                  batch_size=self.settings.ingest_batch_size,
                                  default_tz=self.settings.default_timezone, progress=progress)
                summary = {"mode": mode, "files": res.files, "events_written": res.events,
                           "duplicates": res.duplicate_events, "elapsed_s": res.elapsed_s}
            else:
                def on_file(path: str, action: str, events: int) -> None:
                    self.publish("new_file", {"path": path, "action": action,
                                              "events_written": events})

                res = incremental_ingest(cursor, self.log_root, paths=paths,
                                         batch_size=self.settings.ingest_batch_size,
                                         default_tz=self.settings.default_timezone,
                                         on_file=on_file)
                if quiet and not res.changes:  # periodic rescan found nothing: stay silent
                    silent = True
                    with self._lock:
                        self.state.update({k: v for k, v in quiet_previous.items()
                                           if k != "running"})
                    return
                summary = {"mode": mode, "files_checked": res.files_checked,
                           "files_new": res.files_new, "files_appended": res.files_appended,
                           "files_rewritten": res.files_rewritten,
                           "files_duplicate": res.files_duplicate,
                           "events_written": res.events_written,
                           "duplicates": res.duplicate_events, "elapsed_s": res.elapsed_s}
            self.state["last_result"] = summary
            self.publish("done", summary)
            if self.settings.auto_analysis:
                self._analyze(cursor)
        except Exception as exc:  # noqa: BLE001  report, never kill the API
            self.state["error"] = f"{type(exc).__name__}: {exc}"
            self.publish("error", {"mode": mode, "error": self.state["error"]})
        finally:
            cursor.close()
            self._release(finished=not silent)

    def _release(self, finished: bool) -> None:
        """End of a background run: free the manager and start what was queued meanwhile."""
        with self._lock:
            self.state["running"] = False
            if finished:
                self.state["finished_at"] = _now()
            queued, self._queued_paths = sorted(self._queued_paths), set()
            if queued:
                self._start_locked("incremental", queued, quiet=True)

    def _run_analysis(self) -> None:
        cursor = self.con.cursor()
        try:
            self._analyze(cursor)
        finally:
            cursor.close()
            self._release(finished=False)

    def _analyze(self, cursor: duckdb.DuckDBPyConnection) -> None:
        """Run the analysis. A failure is reported but never fails the ingest."""
        self.analysis.update(running=True, started_at=_now(), error=None)
        try:
            result = pipeline.run_analysis(cursor)
            self.analysis.update(elapsed_s=result.elapsed_s, counts=result.counts)
            self.publish("analysis", {"elapsed_s": result.elapsed_s, **result.counts})
        except Exception as exc:
            log.exception("analysis failed")
            self.analysis["error"] = f"{type(exc).__name__}: {exc}"
            self.publish("error", {"mode": "analysis", "error": self.analysis["error"]})
        finally:
            self.analysis.update(running=False, finished_at=_now())
