"""GET /api/suggestions: questions for the assistant, derived from the logs (P1)."""

from typing import Annotated, Literal

import duckdb
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from logtracer.api.deps import get_cursor
from logtracer.api.schemas import UtcDatetime
from logtracer.services import suggestion_service

router = APIRouter(tags=["suggestions"])

Cursor = Annotated[duckdb.DuckDBPyConnection, Depends(get_cursor)]


class Suggestion(BaseModel):
    kind: str
    question: str
    reason: str
    job_id: str | None = None
    event_id: int | None = None
    last_ts: UtcDatetime = None


class Suggestions(BaseModel):
    scope: Literal["logs", "event"]
    event_id: int | None = None
    items: list[Suggestion]


@router.get("/suggestions", response_model=Suggestions)
def get_suggestions(
    con: Cursor,
    event_id: int | None = Query(None, description="questions about this event (events.id)"),
    lang: Literal["en", "de"] = "en",
    limit: int = Query(8, ge=1, le=20),
) -> dict:
    if event_id is None:
        return {"scope": "logs",
                "items": suggestion_service.suggest_from_logs(con, limit=limit, lang=lang)}
    items = suggestion_service.suggest_for_event(con, event_id, limit=limit, lang=lang)
    if items is None:
        raise HTTPException(404, f"event {event_id} not found")
    return {"scope": "event", "event_id": event_id, "items": items}
