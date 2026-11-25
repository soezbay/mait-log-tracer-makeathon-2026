"""GET /api/trace/{key}: all events of a chain across servers (P2)."""

from typing import Annotated

import duckdb
from fastapi import APIRouter, Depends, HTTPException, Query

from logtracer.api.deps import get_cursor
from logtracer.api.schemas import EventListItem, Page
from logtracer.services import event_service

router = APIRouter(tags=["analysis"])

Cursor = Annotated[duckdb.DuckDBPyConnection, Depends(get_cursor)]


@router.get("/trace/{key}", response_model=Page[EventListItem])
def get_trace(
    con: Cursor, key: str, limit: int = Query(500, ge=1, le=500), offset: int = Query(0, ge=0),
) -> dict:
    """Events with this trace ID, or with this job ID if it is no trace ID, in time order."""
    for column in ("trace_id", "job_id"):
        items, total = event_service.search_events(con, **{column: key}, limit=limit,
                                                   offset=offset)
        if total:
            return {"items": items, "total": total, "limit": limit, "offset": offset}
    raise HTTPException(404, f"no events with trace or job ID {key}")
