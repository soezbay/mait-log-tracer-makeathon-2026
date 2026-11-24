"""LLM tools (MAIT step 2: select context deliberately, never read all logs).

``ToolBox`` runs one tool call against the database and returns a small JSON-safe dict. It also remembers
every event ``id`` it has shown to the model, so ``submit_answer`` can reject IDs the model never saw.
"""
from __future__ import annotations

import json
import logging
from collections.abc import Callable
from typing import Any

import duckdb

from .data_access import LogStore
from .providers.base import ToolSpec

log = logging.getLogger(__name__)

MAX_RESULT_CHARS = 9000

_TIME = (
    "ISO-8601 UTC, e.g. 2026-11-24T08:30:00Z. A bare date like 2026-11-24 means that whole day."
)


def _spec(name: str, description: str, properties: dict[str, Any], required: list[str] | None = None) -> ToolSpec:
    return ToolSpec(
        name=name,
        description=description,
        parameters={"type": "object", "properties": properties, "required": required or []},
    )


TOOL_SPECS: list[ToolSpec] = [
    _spec(
        "get_stats",
        "Overview of the logs in a time range: events, errors and warnings per server and the noisiest "
        "components. Good first step when the question names no job, ID or server.",
        {
            "time_from": {"type": "string", "description": _TIME},
            "time_to": {"type": "string", "description": _TIME},
        },
    ),
    _spec(
        "get_incidents",
        "Incidents = error groups from several servers that were linked as one problem. Start here for "
        "'what went wrong' questions.",
        {
            "time_from": {"type": "string", "description": _TIME},
            "time_to": {"type": "string", "description": _TIME},
            "limit": {"type": "integer", "description": "max rows, default 20"},
        },
    ),
    _spec(
        "get_error_groups",
        "Error groups: many ERROR/WARN lines that share one cause, with status 'recovered' (a retry "
        "succeeded, NOT the cause of a failure) or 'failed'. Use instead of counting single ERRORs. "
        "Returns sample_event_ids you can cite.",
        {
            "time_from": {"type": "string", "description": _TIME},
            "time_to": {"type": "string", "description": _TIME},
            "status": {"type": "string", "description": "recovered | failed | unknown"},
            "server": {"type": "string", "description": "server/host name or part of it"},
            "limit": {"type": "integer", "description": "max rows, default 20"},
        },
    ),
    _spec(
        "get_anomalies",
        "Statistical anomalies: error-rate spikes, rare/new message types, duration outliers.",
        {
            "time_from": {"type": "string", "description": _TIME},
            "time_to": {"type": "string", "description": _TIME},
            "server": {"type": "string"},
            "limit": {"type": "integer"},
        },
    ),
    _spec(
        "search_events",
        "Search individual log events. All filters are optional and combined with AND. Results are sorted "
        "by time and capped. Use narrow filters.",
        {
            "server": {"type": "string", "description": "server/host name or part of it"},
            "component": {"type": "string", "description": "component name or part of it"},
            "level": {"type": "string", "description": "DEBUG, INFO, WARN, ERROR, FATAL; comma-separated for several"},
            "time_from": {"type": "string", "description": _TIME},
            "time_to": {"type": "string", "description": _TIME},
            "text": {"type": "string", "description": "substring of the message (case-insensitive)"},
            "job_id": {"type": "string"},
            "trace_id": {"type": "string"},
            "limit": {"type": "integer", "description": "max rows, default 20, max 50"},
        },
    ),
    _spec(
        "trace",
        "All events that belong to one key across all servers, in time order: a job_id, trace_id, "
        "session_id or an object ID such as DEMO-Seal-17/C. Shows time clusters, because the same job "
        "number does not always mean the same job.",
        {"key": {"type": "string", "description": "job_id, trace_id, session_id or object ID"}},
        ["key"],
    ),
    _spec(
        "correlate",
        "Error groups linked to the given error group (same job/trace, same object, close in time, "
        "dependency=<host>), with the link type (hard/soft) and confidence.",
        {"group_id": {"type": "integer", "description": "group_id from get_error_groups"}},
        ["group_id"],
    ),
    _spec(
        "get_context",
        "Lines around one event in the same log file, and optionally WARN/ERROR events on OTHER servers "
        "within a time window (use window_seconds to find cross-system causes).",
        {
            "event_id": {"type": "integer", "description": "internal `id` of an event from another tool"},
            "n": {"type": "integer", "description": "lines before/after in the same file, default 5, max 25"},
            "window_seconds": {"type": "integer", "description": "look at other servers +/- this many seconds, 0=off, max 3600"},
        },
        ["event_id"],
    ),
]

_LABELS = {
    "get_stats": "Getting an overview of the logs",
    "get_incidents": "Looking at correlated incidents",
    "get_error_groups": "Reading error groups",
    "get_anomalies": "Checking anomalies",
    "search_events": "Searching events",
    "trace": "Tracing across servers",
    "correlate": "Looking up linked error groups",
    "get_context": "Reading the context around an event",
}


def step_label(name: str, args: dict[str, Any]) -> str:
    detail = next((str(args[k]) for k in ("key", "server", "job_id", "trace_id", "text", "event_id", "group_id") if args.get(k)), "")
    base = _LABELS.get(name, name)
    return f"{base}: {detail}…" if detail else f"{base}…"


def summarize(result: dict[str, Any]) -> str:
    if "error" in result:
        return f"error: {result['error']}"[:200]
    if "total_matches" in result:
        t, r = result["total_matches"], result.get("returned", 0)
        return f"{r} of {t} rows"
    if "linked_groups" in result:
        return f"{result.get('returned', 0)} linked groups"
    if "event" in result:
        return "context loaded"
    return "ok"


def collect_event_ids(obj: Any) -> set[int]:
    """Event IDs shown to the model: ``id`` of event rows and every ``*event_ids`` list."""
    found: set[int] = set()
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k == "id" and isinstance(v, int) and not isinstance(v, bool):
                found.add(v)
            elif k.endswith("event_ids") and isinstance(v, list):
                found.update(x for x in v if isinstance(x, int))
            else:
                found |= collect_event_ids(v)
    elif isinstance(obj, list):
        for item in obj:
            found |= collect_event_ids(item)
    return found


def _json_safe(obj: Any) -> Any:
    return json.loads(json.dumps(obj, default=str))


def _fit(result: dict[str, Any]) -> dict[str, Any]:
    """Drop trailing rows until the JSON is small enough for the model."""
    rows = result.get("rows")
    if not isinstance(rows, list):
        return result
    while rows and len(json.dumps(result, default=str)) > MAX_RESULT_CHARS:
        rows.pop()
        result["truncated"] = True
        result["returned"] = len(rows)
    return result


class ToolBox:
    def __init__(self, store: LogStore):
        self.store = store
        self.seen_event_ids: set[int] = set()
        self._handlers: dict[str, Callable[..., dict[str, Any]]] = {
            "get_stats": store.stats,
            "get_incidents": lambda **kw: store.incidents(**kw),
            "get_error_groups": lambda **kw: store.error_groups(**kw),
            "get_anomalies": lambda **kw: store.anomalies(**kw),
            "search_events": lambda **kw: store.search_events(**kw),
            "trace": lambda key, **kw: store.trace(key),
            "correlate": lambda group_id, **kw: store.correlations(int(group_id)),
            "get_context": lambda event_id, n=5, window_seconds=0, **kw: store.context(int(event_id), n, window_seconds),
        }

    @property
    def specs(self) -> list[ToolSpec]:
        return TOOL_SPECS

    def execute(self, name: str, args: dict[str, Any] | None) -> dict[str, Any]:
        args = {k: v for k, v in (args or {}).items() if v not in (None, "")}
        handler = self._handlers.get(name)
        if handler is None:
            return {"error": f"Unknown tool {name!r}.", "available_tools": sorted(self._handlers)}
        try:
            result = handler(**args)
        except TypeError as exc:
            return {"error": f"Bad arguments for {name}: {exc}"}
        except ValueError as exc:
            return {"error": str(exc)}
        except duckdb.CatalogException as exc:
            log.warning("tool %s: missing table: %s", name, exc)
            return {
                "error": "This data is not available yet (table missing).",
                "hint": "Use search_events / trace on raw events instead.",
            }
        except duckdb.Error as exc:
            log.exception("tool %s failed", name)
            return {"error": f"Database error while running {name}: {str(exc)[:200]}"}
        result = _fit(_json_safe(result))
        self.seen_event_ids |= collect_event_ids(result)
        return result
