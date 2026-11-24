"""Response models of the P1 endpoints (interface 2; examples in contracts/examples/)."""

from datetime import datetime
from typing import Annotated, Any

from pydantic import BaseModel, PlainSerializer


def _iso_utc(value: datetime | None) -> str | None:
    """Naive UTC datetimes from DuckDB -> ISO 8601 with Z, seconds precision unless needed."""
    if value is None:
        return None
    text = value.isoformat(timespec="milliseconds" if value.microsecond else "seconds")
    return f"{text}Z"


UtcDatetime = Annotated[datetime | None, PlainSerializer(_iso_utc, return_type=str | None)]


class Page[T](BaseModel):
    items: list[T]
    total: int
    limit: int
    offset: int


class Stats(BaseModel):
    servers: int
    sources: int
    unique_sources: int
    duplicate_sources: int
    events: int
    duplicate_events: int
    late_events: int
    tz_assumed_events: int
    unparsed_events: int
    levels: dict[str, int]
    time_range: dict[str, UtcDatetime]
    last_ingest_at: UtcDatetime = None


class Source(BaseModel):
    source_id: int
    path: str
    server: str
    os: str | None
    application: str | None
    component: str | None
    format: str | None
    encoding: str | None
    compressed: bool
    size: int | None
    sha256: str | None
    duplicate_of: int | None
    event_count: int
    checkpoint_bytes: int
    checkpoint_line: int
    ingested_at: UtcDatetime = None


class EventListItem(BaseModel):
    id: int
    ts_utc: UtcDatetime = None
    host: str | None
    component: str | None
    level: str | None
    event_id: str | None
    job_id: str | None
    trace_id: str | None
    message: str | None
    source_path: str
    line_start: int
    line_end: int
    is_duplicate: bool
    is_late: bool


class EventDetail(BaseModel):
    id: int
    source_id: int
    source_path: str
    format: str | None
    encoding: str | None
    line_start: int
    line_end: int
    ts_raw: str | None
    ts_utc: UtcDatetime = None
    tz_assumed: bool
    clock_offset_s: float
    host: str | None
    component: str | None
    level: str | None
    level_raw: str | None
    event_id: str | None
    job_id: str | None
    trace_id: str | None
    session_id: str | None
    message: str | None
    attrs: dict[str, Any]
    template_id: int | None
    fingerprint: str | None
    duplicate_of: int | None
    is_late: bool
    parse_error: str | None
    raw: str


class ContextLine(BaseModel):
    no: int
    is_event: bool
    text: str


class EventContext(BaseModel):
    id: int
    source_path: str
    format: str | None
    encoding: str
    line_start: int
    line_end: int
    lines: list[ContextLine]
