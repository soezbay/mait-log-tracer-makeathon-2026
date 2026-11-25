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
TRACE_FAILURES_MAX = 8  # more failing lines than this: the job is too big to require citing each

_TIME = {"type": "string", "description": "UTC time or date"}
_LIMIT = {"type": "integer", "description": "max rows (default 20)"}


def _spec(name: str, description: str, properties: dict[str, Any],
          required: list[str] | None = None) -> ToolSpec:
    return ToolSpec(
        name=name,
        description=description,
        parameters={"type": "object", "properties": properties, "required": required or []},
    )


TOOL_SPECS: list[ToolSpec] = [
    _spec(
        "get_stats",
        "Events, errors and warnings per server and the noisiest components. First step when the "
        "question names no job, id or server.",
        {"time_from": _TIME, "time_to": _TIME},
    ),
    _spec(
        "get_incidents",
        "Incidents: error groups from several servers linked as one problem. steps are in time order; "
        "cite sample_event_ids (one per step), never incident_id or group_ids.",
        {"time_from": _TIME, "time_to": _TIME, "limit": _LIMIT},
    ),
    _spec(
        "get_error_groups",
        "Error groups: ERROR/WARN lines sharing one cause, status recovered (harmless) or failed.",
        {"time_from": _TIME, "time_to": _TIME, "status": {"type": "string"},
         "server": {"type": "string"}, "limit": _LIMIT},
    ),
    _spec(
        "get_anomalies",
        "Statistical anomalies: error-rate spikes, new message types, duration outliers.",
        {"time_from": _TIME, "time_to": _TIME, "server": {"type": "string"}, "limit": _LIMIT},
    ),
    _spec(
        "search_events",
        "Find log events; filters combine with AND. text searches the whole original log line "
        "(message and all fields).",
        {
            "server": {"type": "string"},
            "component": {"type": "string"},
            "level": {"type": "string", "description": "e.g. ERROR or WARN,ERROR"},
            "time_from": _TIME,
            "time_to": _TIME,
            "text": {"type": "string"},
            "job_id": {"type": "string"},
            "trace_id": {"type": "string"},
            "limit": {"type": "integer", "description": "max rows (default 20, max 50)"},
        },
    ),
    _spec(
        "trace",
        "Everything for one key across all servers: job_id, trace_id, session_id or object id. "
        "Also lists related keys (e.g. re-runs) and time clusters. Best first step for a named job.",
        {"key": {"type": "string"}},
        ["key"],
    ),
    _spec(
        "correlate",
        "Error groups linked to one error group, with link type and confidence.",
        {"group_id": {"type": "integer"}},
        ["group_id"],
    ),
    _spec(
        "get_context",
        "Lines around one event in its file; with window_seconds also WARN/ERROR on other servers.",
        {
            "event_id": {"type": "integer"},
            "n": {"type": "integer", "description": "lines before/after (default 5, max 25)"},
            "window_seconds": {"type": "integer", "description": "other servers +/- seconds (max 3600)"},
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
    """Event IDs shown to the model: ``id`` of event rows and every ``*event_ids`` list.

    Understands both shapes: plain dicts and compact tables ``{"cols": [...], "rows": [[...]]}``.
    """
    found: set[int] = set()
    if isinstance(obj, dict):
        cols, rows = obj.get("cols"), obj.get("rows")
        if isinstance(cols, list) and isinstance(rows, list):
            for i, col in enumerate(cols):
                if col == "id" or (isinstance(col, str) and col.endswith("event_ids")):
                    for row in rows:
                        if isinstance(row, list) and i < len(row):
                            found |= _ints(row[i])
        for k, v in obj.items():
            if k == "rows" and isinstance(cols, list):
                continue
            if k == "id" and isinstance(v, int) and not isinstance(v, bool):
                found.add(v)
            elif k.endswith("event_ids") and isinstance(v, list):
                found |= _ints(v)
            else:
                found |= collect_event_ids(v)
    elif isinstance(obj, list):
        for item in obj:
            found |= collect_event_ids(item)
    return found


def _ints(value: Any) -> set[int]:
    if isinstance(value, bool):
        return set()
    if isinstance(value, int):
        return {value}
    if isinstance(value, list):
        return {x for x in value if isinstance(x, int) and not isinstance(x, bool)}
    return set()


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
        # trace key -> related jobs that logged WARN/ERROR/FATAL (the answer must mention them)
        self.related_failures: dict[str, dict[str, Any]] = {}
        # trace key -> its own WARN/ERROR/FATAL lines, when trace listed all of them (few)
        self.trace_failures: dict[str, list[dict[str, Any]]] = {}
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
        if name == "trace":
            self._remember_related(result)
            self._remember_failures(result)
        return result

    def _remember_failures(self, result: dict[str, Any]) -> None:
        """The job's own WARN/ERROR/FATAL lines, if trace listed them all and there are few."""
        cols, rows = result.get("cols") or [], result.get("rows") or []
        if result.get("truncated") or not {"id", "level"} <= set(cols):
            return
        failing = [
            dict(zip(cols, row, strict=False)) for row in rows
            if str(row[cols.index("level")]).upper() in ("WARN", "ERROR", "FATAL")
        ]
        if 0 < len(failing) <= TRACE_FAILURES_MAX:
            self.trace_failures[str(result.get("key"))] = failing

    def _remember_related(self, result: dict[str, Any]) -> None:
        rel = result.get("related")
        if not isinstance(rel, dict):
            return
        groups = rel.get("groups") or {}
        cols = groups.get("cols") or []
        if "level" not in cols:
            return
        i = cols.index("level")
        if not any(str(row[i]).upper() in ("WARN", "ERROR", "FATAL") for row in groups.get("rows", [])):
            return
        keys = rel.get("keys") or {}
        shown = (keys.get("list") or []) + (keys.get("first") or []) + (keys.get("last") or [])
        self.related_failures[str(result.get("key"))] = {
            "events": rel.get("events"), "count": keys.get("count", len(shown)), "keys": shown,
        }
