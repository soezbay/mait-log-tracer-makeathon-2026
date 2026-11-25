"""API endpoints for the log analysis (P2): incidents, error groups, anomalies, graph."""

from datetime import datetime
from typing import Annotated, Any, Literal

import duckdb
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel

from logtracer.analysis.graph import build_graph
from logtracer.api.deps import get_cursor
from logtracer.api.events import _naive_utc
from logtracer.api.schemas import Page, UtcDatetime
from logtracer.services import analysis_service
from logtracer.storage.repositories import analysis as analysis_repo

Cursor = Annotated[duckdb.DuckDBPyConnection, Depends(get_cursor)]
Status = Literal["failed", "recovered", "unknown"]
From = Annotated[datetime | None, Query(alias="from", description="ISO 8601, UTC if no zone")]
To = Annotated[datetime | None, Query(description="ISO 8601, UTC if no zone")]

router = APIRouter(prefix="/analysis", tags=["analysis"])


class AnalysisStatus(BaseModel):
    running: bool
    started_at: UtcDatetime = None
    finished_at: UtcDatetime = None
    elapsed_s: float | None
    error: str | None
    counts: dict[str, int]  # rows per table


class IncidentJob(BaseModel):
    job_id: str
    runs: int


class Incident(BaseModel):
    incident_id: int
    title: str | None
    first_ts: UtcDatetime = None
    last_ts: UtcDatetime = None
    status: str | None
    hosts: list[str]
    confidence: float | None
    group_count: int
    event_count: int
    root_host: str | None
    root_component: str | None
    root_level: str | None
    root_event_id: int | None
    jobs: list[IncidentJob]


class IncidentStep(BaseModel):
    group_id: int
    is_root: bool
    host: str | None
    component: str | None
    level: str | None
    status: str | None
    count: int
    first_ts: UtcDatetime = None
    last_ts: UtcDatetime = None
    event_id: int | None
    event_ids: list[int]
    message: str | None
    job_id: str | None
    trace_id: str | None
    clock_offset_s: float | None
    source_path: str | None
    line_start: int | None
    line_end: int | None


class IncidentLink(BaseModel):
    group_a: int
    group_b: int
    kind: str
    link_key: str
    lag_s: float
    confidence: float


class Anomaly(BaseModel):
    anomaly_id: int
    host: str | None
    component: str | None
    kind: str | None
    window_start: UtcDatetime = None
    window_end: UtcDatetime = None
    score: float | None
    details: dict[str, Any]


class IncidentDetail(Incident):
    steps: list[IncidentStep]
    links: list[IncidentLink]
    anomalies: list[Anomaly]


class ErrorGroup(BaseModel):
    id: int
    label: str
    status: str | None
    event_ids: list[int]
    host: str | None
    component: str | None
    level: str | None
    count: int
    first_ts: UtcDatetime = None
    last_ts: UtcDatetime = None
    message: str | None


def _status(request: Request, con: duckdb.DuckDBPyConnection) -> dict:
    state = request.app.state.ingest.analysis
    return {**state, "counts": analysis_repo.table_counts(con)}


def _page(items: list[dict], total: int, limit: int, offset: int) -> dict:
    return {"items": items, "total": total, "limit": limit, "offset": offset}


@router.get("/status", response_model=AnalysisStatus)
def analysis_status(request: Request, con: Cursor) -> dict:
    return _status(request, con)


@router.post("/run", status_code=202, response_model=AnalysisStatus)
def run_analysis(request: Request, con: Cursor) -> dict:
    """Rebuild all analysis tables in the background."""
    if not request.app.state.ingest.start_analysis():
        raise HTTPException(409, "an ingest or analysis is already running")
    return _status(request, con)


@router.get("/stats")
def analysis_stats(con: Cursor) -> dict:
    return {"counts": analysis_repo.table_counts(con)}


@router.get("/incidents", response_model=Page[Incident])
def list_incidents(
    con: Cursor,
    from_: From = None,
    to: To = None,
    server: str | None = None,
    status: Status | None = None,
    q: str | None = Query(None, description="text in the title, messages or job IDs"),
    event_id: int | None = Query(None, description="the incident this event belongs to"),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> dict:
    items, total = analysis_service.list_incidents(
        con, server=server, status=status, q=q, event_id=event_id, ts_from=_naive_utc(from_),
        ts_to=_naive_utc(to), limit=limit, offset=offset)
    return _page(items, total, limit, offset)


@router.get("/incidents/{incident_id}", response_model=IncidentDetail)
def incident_detail(con: Cursor, incident_id: int) -> dict:
    incident = analysis_service.get_incident(con, incident_id)
    if incident is None:
        raise HTTPException(404, f"incident {incident_id} not found")
    return incident


@router.get("/groups", response_model=Page[ErrorGroup])
def list_groups(
    con: Cursor, limit: int = Query(100, ge=1, le=500), offset: int = Query(0, ge=0),
) -> dict:
    items, total = analysis_service.list_groups(con, limit, offset)
    return _page(items, total, limit, offset)


@router.get("/anomalies", response_model=Page[Anomaly])
def list_anomalies(
    con: Cursor,
    from_: From = None,
    to: To = None,
    server: str | None = None,
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> dict:
    items, total = analysis_repo.list_anomalies(
        con, server=server, ts_from=_naive_utc(from_), ts_to=_naive_utc(to), limit=limit,
        offset=offset)
    return _page(items, total, limit, offset)


@router.get("/graph")
def analysis_graph(
    con: Cursor,
    incident_id: int | None = Query(None, description="only the groups of this incident"),
) -> dict:
    if incident_id is None:
        return build_graph(con)
    found = analysis_repo.incident_group_ids(con, incident_id)
    if found is None:
        raise HTTPException(404, f"incident {incident_id} not found")
    return build_graph(con, found[0])
