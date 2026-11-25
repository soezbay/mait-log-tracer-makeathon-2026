"""GET /api/events, /api/events/{id}, /api/events/{id}/context (P1)."""

from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated

import duckdb
from fastapi import APIRouter, Depends, HTTPException, Query

from logtracer.api.deps import get_cursor, get_log_root
from logtracer.api.schemas import EventContext, EventDetail, EventListItem, Page
from logtracer.normalize.levels import LEVELS
from logtracer.services import event_service

router = APIRouter(tags=["events"])

Cursor = Annotated[duckdb.DuckDBPyConnection, Depends(get_cursor)]


def _naive_utc(value: datetime | None) -> datetime | None:
    """Query times with a zone are converted to UTC; times without one are taken as UTC."""
    if value is None or value.tzinfo is None:
        return value
    return value.astimezone(UTC).replace(tzinfo=None)


@router.get("/events", response_model=Page[EventListItem])
def list_events(
    con: Cursor,
    server: str | None = Query(None, description="host name, e.g. mait_win03_cad_converter"),
    component: str | None = None,
    level: str | None = Query(None, description="comma-separated, e.g. ERROR,FATAL"),
    from_: Annotated[datetime | None,
                     Query(alias="from", description="ISO 8601, UTC if no zone")] = None,
    to: Annotated[datetime | None, Query(description="ISO 8601, UTC if no zone")] = None,
    q: str | None = Query(None, description="text search in the message"),
    job_id: str | None = None,
    trace_id: str | None = None,
    source_id: int | None = Query(None, description="only events of this file"),
    include_duplicates: bool = False,
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> dict:
    levels = [x.strip().upper() for x in level.split(",") if x.strip()] if level else None
    if levels and not set(levels) <= set(LEVELS):
        raise HTTPException(422, f"level must be one of {', '.join(LEVELS)}")
    items, total = event_service.search_events(
        con, host=server, component=component, levels=levels, ts_from=_naive_utc(from_),
        ts_to=_naive_utc(to), q=q, job_id=job_id, trace_id=trace_id, source_id=source_id,
        include_duplicates=include_duplicates, limit=limit, offset=offset,
    )
    return {"items": items, "total": total, "limit": limit, "offset": offset}


@router.get("/events/{event_pk}", response_model=EventDetail)
def get_event(con: Cursor, event_pk: int) -> dict:
    event = event_service.get_event(con, event_pk)
    if event is None:
        raise HTTPException(404, f"event {event_pk} not found")
    return event


@router.get("/events/{event_pk}/context", response_model=EventContext)
def get_event_context(
    con: Cursor,
    event_pk: int,
    log_root: Annotated[Path, Depends(get_log_root)],
    n: int = Query(10, ge=0, le=event_service.MAX_CONTEXT_LINES),
) -> dict:
    try:
        context = event_service.get_context(con, log_root, event_pk, n)
    except FileNotFoundError as exc:
        raise HTTPException(404, f"source file not found: {exc.filename}") from exc
    if context is None:
        raise HTTPException(404, f"event {event_pk} not found")
    return context
