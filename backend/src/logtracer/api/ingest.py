"""POST /api/ingest, GET /api/ingest/status, GET /api/ingest/progress (SSE) (P1).

Data sets: POST /api/ingest/upload (a ZIP becomes the analysed data set), POST
/api/ingest/original (back to LOG_ROOT), GET /api/ingest/dataset.
"""

import asyncio
import shutil
from collections.abc import AsyncIterator
from typing import Literal

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.sse import EventSourceResponse, ServerSentEvent
from pydantic import BaseModel

from logtracer.api.schemas import UtcDatetime
from logtracer.services import dataset_service

router = APIRouter(tags=["ingest"])


class IngestRequest(BaseModel):
    mode: Literal["full", "incremental"] = "incremental"


class IngestState(BaseModel):
    running: bool
    mode: str | None
    started_at: UtcDatetime = None
    finished_at: UtcDatetime = None
    last_result: dict | None
    error: str | None
    watcher_enabled: bool


def _state(request: Request) -> dict:
    return {**request.app.state.ingest.state,
            "watcher_enabled": request.app.state.watcher is not None}


@router.post("/ingest", status_code=202, response_model=IngestState)
def start_ingest(request: Request, body: IngestRequest | None = None) -> dict:
    """Start a full rebuild or an incremental ingest in the background."""
    mode = (body or IngestRequest()).mode
    if not request.app.state.ingest.start(mode):
        raise HTTPException(409, "an ingest is already running")
    return _state(request)


@router.get("/ingest/status", response_model=IngestState)
def ingest_status(request: Request) -> dict:
    return _state(request)


@router.get("/ingest/progress", response_class=EventSourceResponse)
async def ingest_progress(request: Request) -> AsyncIterator[ServerSentEvent]:
    """Live events: `state` on connect, then `started`, `progress`, `new_file`, `done`, `error`."""
    manager = request.app.state.ingest
    queue = manager.subscribe()
    try:
        yield ServerSentEvent(event="state", data=IngestState(**_state(request)).model_dump(
            mode="json"))
        while True:
            try:
                event, data = await asyncio.wait_for(queue.get(), timeout=1.0)
            except TimeoutError:
                if await request.is_disconnected():
                    return
                continue
            yield ServerSentEvent(event=event, data=data)
    finally:
        manager.unsubscribe(queue)


class Dataset(BaseModel):
    kind: Literal["original", "upload"]
    name: str
    activated_at: str | None = None
    files: int | None = None


class DatasetState(BaseModel):
    dataset: Dataset
    running: bool
    error: str | None
    last_result: dict | None


def _dataset_state(request: Request) -> dict:
    manager = request.app.state.ingest
    return {"dataset": manager.dataset, "running": manager.state["running"],
            "error": manager.state["error"], "last_result": manager.state["last_result"]}


@router.get("/ingest/dataset", response_model=DatasetState)
def active_dataset(request: Request) -> dict:
    """Which data set the database holds: the original package or an uploaded ZIP."""
    return _dataset_state(request)


@router.post("/ingest/upload", status_code=202, response_model=DatasetState)
async def upload_dataset(request: Request,
                         name: str = Query("upload.zip", max_length=200)) -> dict:
    """Make an uploaded ZIP the analysed data set (body: the ZIP bytes, `application/zip`).

    The ZIP is extracted below `data/uploads/` (log files and server_info.json only, size
    limits, no paths outside the folder) and ingested like the original package, analysis
    included. Answers 202 at once; follow the ingest with /ingest/status or /ingest/progress.
    """
    manager = request.app.state.ingest
    if manager.state["running"]:
        raise HTTPException(409, "an ingest is already running")
    settings = request.app.state.settings
    folder = dataset_service.new_upload_dir(settings, name)
    zip_path = folder / "upload.zip"
    size = 0
    try:
        out = await run_in_threadpool(zip_path.open, "wb")  # file I/O off the event loop
        try:
            async for chunk in request.stream():
                size += len(chunk)
                if size > dataset_service.MAX_UPLOAD_BYTES:
                    raise dataset_service.UploadError(
                        f"The ZIP is larger than {dataset_service.MAX_UPLOAD_BYTES // 2**20} MiB.",
                        413)
                await run_in_threadpool(out.write, chunk)
        finally:
            await run_in_threadpool(out.close)
        if size == 0:
            raise dataset_service.UploadError("The upload is empty.")
        root, files, _skipped = await run_in_threadpool(
            dataset_service.extract_upload, zip_path, folder / "files")
    except dataset_service.UploadError as exc:
        shutil.rmtree(folder, ignore_errors=True)
        raise HTTPException(exc.status, str(exc)) from exc
    finally:
        zip_path.unlink(missing_ok=True)
    dataset = dataset_service.upload_dataset(dataset_service.safe_name(name), root, files)
    if not manager.switch_dataset(dataset):
        shutil.rmtree(folder, ignore_errors=True)
        raise HTTPException(409, "an ingest is already running")
    dataset_service.prune_uploads(settings, keep=root)
    return _dataset_state(request)


@router.post("/ingest/original", status_code=202, response_model=DatasetState)
def restore_original(request: Request) -> dict:
    """Analyse the original package (LOG_ROOT) again: full ingest + analysis."""
    manager = request.app.state.ingest
    if not manager.switch_dataset(dataset_service.original_dataset(request.app.state.settings)):
        raise HTTPException(409, "an ingest is already running")
    return _dataset_state(request)
