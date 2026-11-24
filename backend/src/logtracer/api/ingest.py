"""POST /api/ingest, GET /api/ingest/status, GET /api/ingest/progress (SSE) (P1)."""

import asyncio
from collections.abc import AsyncIterator
from typing import Literal

from fastapi import APIRouter, HTTPException, Request
from fastapi.sse import EventSourceResponse, ServerSentEvent
from pydantic import BaseModel

from logtracer.api.schemas import UtcDatetime

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
