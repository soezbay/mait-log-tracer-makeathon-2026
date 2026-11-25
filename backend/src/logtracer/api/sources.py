"""GET /api/stats, /api/sources and /api/sources/summary (P1)."""

from typing import Annotated

import duckdb
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from logtracer.api.deps import get_cursor
from logtracer.api.schemas import Page, Source, Stats, UtcDatetime
from logtracer.services import event_service
from logtracer.storage.repositories import sources as sources_repo

router = APIRouter(tags=["sources"])

Cursor = Annotated[duckdb.DuckDBPyConnection, Depends(get_cursor)]


@router.get("/stats", response_model=Stats)
def stats(con: Cursor) -> dict:
    return event_service.get_stats(con)


class ServerSummary(BaseModel):
    server: str
    os: str | None
    role: str | None
    files: int
    copies: int
    events: int
    duplicate_events: int
    unparsed_events: int
    errors: int  # real ERROR/FATAL lines, harmless messages left out
    bytes: int
    formats: list[str]
    first_ts: UtcDatetime = None
    last_ts: UtcDatetime = None


class FormatSummary(BaseModel):
    format: str
    files: int
    copies: int
    events: int


class SourceSummary(BaseModel):
    servers: list[ServerSummary]
    formats: list[FormatSummary]


@router.get("/sources/summary", response_model=SourceSummary)
def source_summary(con: Cursor) -> dict:
    return sources_repo.overview(con)


@router.get("/sources", response_model=Page[Source])
def sources(
    con: Cursor,
    server: str | None = None,
    format: str | None = Query(
        None, description="kv_log | bracket_json | csv_semicolon | jsonl | xml_events | freetext"
    ),
    duplicates: bool | None = Query(None, description="true: only copies, false: only originals"),
    q: str | None = Query(None, description="text in the path"),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> dict:
    items, total = event_service.list_sources(
        con, server=server, fmt=format, duplicates=duplicates, q=q, limit=limit, offset=offset
    )
    return {"items": items, "total": total, "limit": limit, "offset": offset}
