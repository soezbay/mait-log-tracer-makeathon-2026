"""GET /api/stats and GET /api/sources (P1)."""

from typing import Annotated

import duckdb
from fastapi import APIRouter, Depends, Query

from logtracer.api.deps import get_cursor
from logtracer.api.schemas import Page, Source, Stats
from logtracer.services import event_service

router = APIRouter(tags=["sources"])

Cursor = Annotated[duckdb.DuckDBPyConnection, Depends(get_cursor)]


@router.get("/stats", response_model=Stats)
def stats(con: Cursor) -> dict:
    return event_service.get_stats(con)


@router.get("/sources", response_model=Page[Source])
def sources(
    con: Cursor,
    server: str | None = None,
    format: str | None = Query(
        None, description="kv_log | bracket_json | csv_semicolon | jsonl | xml_events | freetext"
    ),
    duplicates: bool | None = Query(None, description="true: only copies, false: only originals"),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> dict:
    items, total = event_service.list_sources(
        con, server=server, fmt=format, duplicates=duplicates, limit=limit, offset=offset
    )
    return {"items": items, "total": total, "limit": limit, "offset": offset}
