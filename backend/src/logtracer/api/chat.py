"""POST /chat (SSE) and GET /chat/{conversation_id}. Owned by P3.

Register in main.py:   app.include_router(chat.router, prefix="/api")

Events of the stream:  step (tool call, running/done) · token (interim model text) · answer (structured,
see assistant/answer.py) · done (usage, cost) · error.

Streams use FastAPI's built-in SSE (``fastapi.sse``), as AGENTS.md requires. The frontend reads this
POST stream with ``fetch``, not ``EventSource``.

main.py (P1) calls ``use_connection(app.state.db)`` at startup, so API, ingest and assistant share one
DuckDB connection (DuckDB: one writing process per file). Without it (scripts, some tests) this module
opens DB_PATH once itself via ``storage.db``.
"""
from __future__ import annotations

import logging
import threading
from collections.abc import Callable, Iterator

import duckdb
from fastapi import APIRouter
from fastapi.sse import EventSourceResponse, ServerSentEvent
from pydantic import BaseModel, Field

from ..assistant.agent import LogTracerAgent
from ..assistant.config import get_settings
from ..assistant.data_access import LogStore
from ..assistant.providers import LLMProvider, ProviderError, create_provider
from ..storage import db

log = logging.getLogger(__name__)
router = APIRouter(prefix="/chat", tags=["chat"])

_lock = threading.Lock()
_conn: duckdb.DuckDBPyConnection | None = None
_cursor_factory: Callable[[], duckdb.DuckDBPyConnection] | None = None
_provider_factory: Callable[[], LLMProvider] | None = None


def configure(
    cursor_factory: Callable[[], duckdb.DuckDBPyConnection] | None = None,
    provider_factory: Callable[[], LLMProvider] | None = None,
) -> None:
    """Override the database cursor and/or the LLM provider (used by main.py and by tests)."""
    global _cursor_factory, _provider_factory
    _cursor_factory, _provider_factory = cursor_factory, provider_factory


def use_connection(con: duckdb.DuckDBPyConnection | None) -> None:
    """Use the app's shared connection for all chat cursors (None: back to the module's own)."""
    global _cursor_factory
    _cursor_factory = con.cursor if con is not None else None


def _default_cursor() -> duckdb.DuckDBPyConnection:
    global _conn
    with _lock:
        if _conn is None:
            _conn = db.connect(get_settings().db_path)
            db.init_schema(_conn)  # idempotent; makes sure the assistant tables exist
        return _conn.cursor()


def _cursor() -> duckdb.DuckDBPyConnection:
    return (_cursor_factory or _default_cursor)()


def _provider() -> LLMProvider:
    return (_provider_factory or (lambda: create_provider(get_settings())))()


class ChatRequest(BaseModel):
    question: str = Field(min_length=3, max_length=2000)
    conversation_id: str | None = Field(default=None, max_length=64)


def _sse(event: str, data: dict) -> ServerSentEvent:
    return ServerSentEvent(event=event, data=data)


def _stream(req: ChatRequest) -> Iterator[ServerSentEvent]:
    cur = None
    try:
        cur = _cursor()
        store = LogStore(cur)
        history: list[tuple[str, str]] = []
        if req.conversation_id:
            rows = store.history(req.conversation_id)
            pairs = [(rows[i]["content"], rows[i + 1]["content"]) for i in range(0, len(rows) - 1, 2)
                     if rows[i]["role"] == "user" and rows[i + 1]["role"] == "assistant"]
            history = pairs[-3:]
        agent = LogTracerAgent(_provider(), store)
        for ev in agent.run(req.question, conversation_id=req.conversation_id, history=history):
            yield _sse(ev["event"], ev["data"])
    except ProviderError as exc:
        yield _sse("error", {"message": str(exc)})
    except Exception as exc:
        log.exception("chat stream failed")
        yield _sse("error", {"message": f"Internal error: {type(exc).__name__}"})
    finally:
        if cur is not None:
            try:
                cur.close()
            except Exception as exc:  # noqa: BLE001
                log.debug("closing cursor failed: %s", exc)


@router.post("", response_class=EventSourceResponse)
def chat(req: ChatRequest) -> Iterator[ServerSentEvent]:
    yield from _stream(req)


@router.get("/{conversation_id}")
def history(conversation_id: str) -> dict:
    cur = _cursor()
    try:
        return {"conversation_id": conversation_id, "messages": LogStore(cur).history(conversation_id)}
    finally:
        cur.close()
