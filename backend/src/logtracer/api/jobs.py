"""GET /api/jobs, /api/jobs/{id}, /api/jobs/{id}/events: jobs over all events (P1)."""

from datetime import datetime
from typing import Annotated, Literal

import duckdb
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from logtracer.api.deps import get_cursor
from logtracer.api.events import _naive_utc
from logtracer.api.schemas import EventListItem, Page, UtcDatetime
from logtracer.storage.repositories import jobs as jobs_repo

router = APIRouter(tags=["jobs"])

Cursor = Annotated[duckdb.DuckDBPyConnection, Depends(get_cursor)]
Status = Literal["failed", "warning", "recovered", "ok"]
Sort = Literal["problems", "recent", "oldest", "duration", "errors", "job"]


class Job(BaseModel):
    job_pk: int
    job_id: str
    trace_id: str | None
    runs: int
    status: Status
    first_ts: UtcDatetime = None
    last_ts: UtcDatetime = None
    hosts: list[str]
    events: int
    errors: int
    warnings: int
    problem_event_id: int | None
    problem: str | None
    conversion: bool
    incident_id: int | None


class JobPage(Page[Job]):
    by_status: dict[str, int]  # with all filters except the status
    servers: list[str]  # for the server filter


def _job(con: duckdb.DuckDBPyConnection, job_pk: int) -> dict:
    job = jobs_repo.get(con, job_pk)
    if job is None:
        raise HTTPException(404, f"job {job_pk} not found")
    return job


@router.get("/jobs", response_model=JobPage)
def list_jobs(
    con: Cursor,
    status: Status | None = None,
    server: str | None = None,
    q: str | None = Query(None, description="job ID, trace ID or problem text"),
    conversion: bool = Query(False, description="only conversion jobs"),
    from_: Annotated[datetime | None, Query(alias="from")] = None,
    to: datetime | None = None,
    sort: Sort = "problems",
    limit: int = Query(25, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> dict:
    items, total, by_status = jobs_repo.search(
        con, status=status, server=server, q=q, conversion=conversion, ts_from=_naive_utc(from_),
        ts_to=_naive_utc(to), sort=sort, limit=limit, offset=offset)
    return {"items": items, "total": total, "limit": limit, "offset": offset,
            "by_status": by_status, "servers": jobs_repo.server_names(con)}


@router.get("/jobs/{job_pk}", response_model=Job)
def get_job(con: Cursor, job_pk: int) -> dict:
    return _job(con, job_pk)


@router.get("/jobs/{job_pk}/events", response_model=Page[EventListItem])
def get_job_events(
    con: Cursor,
    job_pk: int,
    problems: bool = Query(False, description="only WARN, ERROR and FATAL"),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> dict:
    items, total = jobs_repo.events(con, _job(con, job_pk), errors_only=problems, limit=limit,
                                    offset=offset)
    return {"items": items, "total": total, "limit": limit, "offset": offset}
