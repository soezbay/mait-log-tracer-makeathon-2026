"""All SQL the assistant needs, in one place.

The column names follow ``storage/schema.sql`` (P1 owns it; analysis tables P2, assistant tables P3).
If the schema changes, adjust the queries in this file only. Every public method returns plain,
JSON-friendly dicts that are small enough to hand to an LLM.
"""
from __future__ import annotations

import json
import logging
from datetime import UTC, datetime, timedelta
from typing import Any

import duckdb

log = logging.getLogger(__name__)

MAX_LIMIT = 50
MSG_CHARS = 300
CLUSTER_GAP = timedelta(minutes=30)


# ---------------------------------------------------------------- helpers
def parse_ts(value: str | None, *, end_of_day: bool = False) -> datetime | None:
    """ISO-8601 (UTC) -> naive UTC datetime. A bare date means the whole day."""
    if not value:
        return None
    text = value.strip()
    date_only = len(text) == 10
    try:
        dt = datetime.fromisoformat(text)  # Python 3.11+ accepts a trailing Z
    except ValueError as exc:
        raise ValueError(f"Not an ISO-8601 time: {value!r} (use e.g. 2026-11-24T08:30:00Z)") from exc
    if dt.tzinfo is not None:
        dt = dt.astimezone(UTC).replace(tzinfo=None)
    if date_only and end_of_day:
        dt += timedelta(days=1)
    return dt


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def iso(dt: Any) -> str | None:
    if dt is None:
        return None
    if isinstance(dt, str):
        return dt
    if dt.tzinfo is not None:
        dt = dt.astimezone(UTC).replace(tzinfo=None)
    return dt.isoformat(timespec="seconds") + "Z"


def _clip(limit: int | None, default: int = 20) -> int:
    try:
        n = int(limit) if limit is not None else default
    except (TypeError, ValueError):
        n = default
    return max(1, min(n, MAX_LIMIT))


def _like(value: str) -> str:
    return f"%{value.strip()}%"


def _short(text: str | None, n: int = MSG_CHARS) -> str | None:
    if text is None:
        return None
    text = " ".join(str(text).split())
    return text if len(text) <= n else text[: n - 1] + "…"


class LogStore:
    """Read/write access for the assistant on top of a DuckDB connection or cursor."""

    def __init__(self, cur: duckdb.DuckDBPyConnection):
        self.cur = cur

    # -------------------------------------------------- low level
    def _rows(self, sql: str, params: list[Any] | None = None) -> list[dict[str, Any]]:
        res = self.cur.execute(sql, params or [])
        cols = [d[0] for d in res.description]
        return [dict(zip(cols, row)) for row in res.fetchall()]

    def _scalar(self, sql: str, params: list[Any] | None = None) -> Any:
        row = self.cur.execute(sql, params or []).fetchone()
        return row[0] if row else None

    def _next_id(self, table: str, column: str) -> int:
        return int(self._scalar(f"SELECT COALESCE(MAX({column}), 0) + 1 FROM {table}"))

    @staticmethod
    def _event(r: dict[str, Any]) -> dict[str, Any]:
        out = {
            "id": r["id"],
            "ts": iso(r["ts_utc"]),
            "host": r["host"],
            "component": r["component"],
            "level": r["level"],
            "log_event_code": r.get("event_id"),
            "job_id": r.get("job_id"),
            "trace_id": r.get("trace_id"),
            "message": _short(r.get("message")),
        }
        off = r.get("clock_offset_s")
        if off:
            out["clock_offset_s"] = off  # time was corrected by this many seconds
        return {k: v for k, v in out.items() if v is not None}

    _EVENT_COLS = (
        "e.id, e.ts_utc, e.host, e.component, e.level, e.event_id, e.job_id, e.trace_id, "
        "e.message, e.clock_offset_s"
    )
    _EVENT_FROM = "FROM events e LEFT JOIN sources s ON s.source_id = e.source_id"

    # -------------------------------------------------- events
    def search_events(
        self,
        *,
        server: str | None = None,
        component: str | None = None,
        level: str | None = None,
        time_from: str | None = None,
        time_to: str | None = None,
        text: str | None = None,
        job_id: str | None = None,
        trace_id: str | None = None,
        limit: int | None = None,
    ) -> dict[str, Any]:
        where, params = ["e.duplicate_of IS NULL"], []
        if server:
            where.append("(e.host ILIKE ? OR s.server ILIKE ?)")
            params += [_like(server)] * 2
        if component:
            where.append("e.component ILIKE ?")
            params.append(_like(component))
        if level:
            levels = [x.strip().upper() for x in level.split(",") if x.strip()]
            where.append(f"upper(e.level) IN ({','.join('?' * len(levels))})")
            params += levels
        if (t := parse_ts(time_from)) is not None:
            where.append("e.ts_utc >= ?")
            params.append(t)
        if (t := parse_ts(time_to, end_of_day=True)) is not None:
            where.append("e.ts_utc <= ?")
            params.append(t)
        if text:
            where.append("e.message ILIKE ?")
            params.append(_like(text))
        if job_id:
            where.append("upper(e.job_id) = upper(?)")
            params.append(job_id.strip())
        if trace_id:
            where.append("e.trace_id = ?")
            params.append(trace_id.strip())
        clause = " AND ".join(where)
        total = self._scalar(f"SELECT count(*) {self._EVENT_FROM} WHERE {clause}", params)
        n = _clip(limit)
        rows = self._rows(
            f"SELECT {self._EVENT_COLS} {self._EVENT_FROM} WHERE {clause} ORDER BY e.ts_utc, e.id LIMIT {n}",
            params,
        )
        return {
            "total_matches": total,
            "returned": len(rows),
            "truncated": total > len(rows),
            "rows": [self._event(r) for r in rows],
        }

    def trace(self, key: str, limit: int | None = None) -> dict[str, Any]:
        key = key.strip()
        n = _clip(limit, 40)
        clause = (
            "e.duplicate_of IS NULL AND (upper(e.job_id) = upper(?) OR e.trace_id = ? OR e.session_id = ? "
            "OR e.message ILIKE ? OR e.attrs ILIKE ?)"
        )
        params = [key, key, key, _like(key), _like(key)]
        total = self._scalar(f"SELECT count(*) {self._EVENT_FROM} WHERE {clause}", params)
        rows = self._rows(
            f"SELECT {self._EVENT_COLS} {self._EVENT_FROM} WHERE {clause} ORDER BY e.ts_utc, e.id LIMIT {n}",
            params,
        )
        # Same job number does not always mean the same job: split into time clusters.
        clusters: list[dict[str, Any]] = []
        for r in rows:
            ts = r["ts_utc"]
            if clusters and ts is not None and ts - clusters[-1]["_last"] <= CLUSTER_GAP:
                c = clusters[-1]
                c["_last"], c["end"], c["events"] = ts, iso(ts), c["events"] + 1
                c["hosts"].add(r["host"])
            elif ts is not None:
                clusters.append({"_last": ts, "start": iso(ts), "end": iso(ts), "events": 1, "hosts": {r["host"]}})
        for c in clusters:
            c.pop("_last")
            c["hosts"] = sorted(h for h in c["hosts"] if h)
        out: dict[str, Any] = {
            "key": key,
            "total_matches": total,
            "returned": len(rows),
            "truncated": total > len(rows),
            "time_clusters": clusters,
            "rows": [self._event(r) for r in rows],
        }
        if len(clusters) > 1:
            out["warning"] = (
                "Events with this key fall into several separate time clusters. The same job number does not "
                "always mean the same job: check host, time and object before treating them as one chain."
            )
        return out

    def context(self, event_id: int, n: int = 5, window_seconds: int = 0) -> dict[str, Any]:
        center = self._rows(
            f"SELECT {self._EVENT_COLS}, e.source_id, e.line_start {self._EVENT_FROM} WHERE e.id = ?", [event_id]
        )
        if not center:
            return {"error": f"No event with id {event_id}."}
        c = center[0]
        n = max(0, min(int(n), 25))
        same_file: list[dict[str, Any]] = []
        if c.get("source_id") is not None and c.get("line_start") is not None:
            same_file = self._rows(
                f"SELECT {self._EVENT_COLS} {self._EVENT_FROM} WHERE e.source_id = ? AND e.line_start BETWEEN ? AND ? "
                "AND e.id <> ? ORDER BY e.line_start",
                [c["source_id"], c["line_start"] - n, c["line_start"] + n, event_id],
            )
        out: dict[str, Any] = {
            "event": self._event(c),
            "same_file_neighbours": [self._event(r) for r in same_file],
        }
        window = max(0, min(int(window_seconds or 0), 3600))
        if window and c["ts_utc"] is not None:
            others = self._rows(
                f"SELECT {self._EVENT_COLS} {self._EVENT_FROM} WHERE e.duplicate_of IS NULL AND e.host <> ? "
                "AND e.ts_utc BETWEEN ? AND ? AND upper(e.level) IN ('WARN','ERROR','FATAL') "
                "ORDER BY e.ts_utc, e.id LIMIT 15",
                [c["host"], c["ts_utc"] - timedelta(seconds=window), c["ts_utc"] + timedelta(seconds=window)],
            )
            out["other_servers_warn_error_in_window"] = [self._event(r) for r in others]
        return out

    def stats(self, time_from: str | None = None, time_to: str | None = None) -> dict[str, Any]:
        where, params = ["duplicate_of IS NULL"], []
        if (t := parse_ts(time_from)) is not None:
            where.append("ts_utc >= ?")
            params.append(t)
        if (t := parse_ts(time_to, end_of_day=True)) is not None:
            where.append("ts_utc <= ?")
            params.append(t)
        clause = " AND ".join(where)
        by_host = self._rows(
            "SELECT host, count(*) AS events, "
            "count(*) FILTER (WHERE upper(level) IN ('ERROR','FATAL')) AS errors, "
            "count(*) FILTER (WHERE upper(level) = 'WARN') AS warnings "
            f"FROM events WHERE {clause} GROUP BY host ORDER BY errors DESC, events DESC LIMIT 30",
            params,
        )
        top = self._rows(
            "SELECT host, component, count(*) AS errors FROM events "
            f"WHERE {clause} AND upper(level) IN ('ERROR','FATAL') "
            "GROUP BY host, component ORDER BY errors DESC LIMIT 10",
            params,
        )
        span = self._rows(f"SELECT min(ts_utc) AS first_ts, max(ts_utc) AS last_ts FROM events WHERE {clause}", params)[0]
        return {
            "data_time_range": {"first": iso(span["first_ts"]), "last": iso(span["last_ts"])},
            "by_host": by_host,
            "top_error_components": top,
        }

    # -------------------------------------------------- analysis tables (from P2)
    # error_groups has no title column: the template text (P2, Drain3) serves as the title.
    _TEMPLATE_JOIN = "LEFT JOIN templates t ON t.template_id = g.template_id"

    def error_groups(
        self,
        *,
        time_from: str | None = None,
        time_to: str | None = None,
        status: str | None = None,
        server: str | None = None,
        limit: int | None = None,
    ) -> dict[str, Any]:
        where, params = ["1=1"], []
        if (t := parse_ts(time_to, end_of_day=True)) is not None:
            where.append("g.first_ts <= ?")
            params.append(t)
        if (t := parse_ts(time_from)) is not None:
            where.append("g.last_ts >= ?")
            params.append(t)
        if status:
            where.append("lower(g.status) = lower(?)")
            params.append(status.strip())
        if server:
            where.append("g.host ILIKE ?")
            params.append(_like(server))
        clause = " AND ".join(where)
        total = self._scalar(f"SELECT count(*) FROM error_groups g WHERE {clause}", params)
        rows = self._rows(
            "SELECT g.group_id, g.host, g.component, g.level, t.template AS title, g.first_ts, g.last_ts, "
            "g.count AS event_count, g.status, "
            "COALESCE((SELECT list(m.event_pk) FROM (SELECT event_pk FROM group_members WHERE group_id = g.group_id "
            "ORDER BY event_pk LIMIT 3) m), list_slice(g.sample_event_ids, 1, 3)) AS sample_event_ids "
            f"FROM error_groups g {self._TEMPLATE_JOIN} WHERE {clause} "
            f"ORDER BY g.count DESC, g.first_ts LIMIT {_clip(limit)}",
            params,
        )
        for r in rows:
            r["first_ts"], r["last_ts"] = iso(r["first_ts"]), iso(r["last_ts"])
            r["title"] = _short(r["title"])
            r["sample_event_ids"] = r["sample_event_ids"] or []
        return {"total_matches": total, "returned": len(rows), "truncated": total > len(rows), "rows": rows}

    def anomalies(
        self,
        *,
        time_from: str | None = None,
        time_to: str | None = None,
        server: str | None = None,
        limit: int | None = None,
    ) -> dict[str, Any]:
        where, params = ["1=1"], []
        if (t := parse_ts(time_to, end_of_day=True)) is not None:
            where.append("window_start <= ?")
            params.append(t)
        if (t := parse_ts(time_from)) is not None:
            where.append("window_end >= ?")
            params.append(t)
        if server:
            where.append("host ILIKE ?")
            params.append(_like(server))
        clause = " AND ".join(where)
        total = self._scalar(f"SELECT count(*) FROM anomalies WHERE {clause}", params)
        rows = self._rows(
            "SELECT anomaly_id, host, component, kind, score, window_start AS ts_start, "
            "window_end AS ts_end, CAST(details AS VARCHAR) AS description "
            f"FROM anomalies WHERE {clause} ORDER BY score DESC LIMIT {_clip(limit)}",
            params,
        )
        for r in rows:
            r["ts_start"], r["ts_end"] = iso(r["ts_start"]), iso(r["ts_end"])
            r["description"] = _short(r["description"])
        return {"total_matches": total, "returned": len(rows), "truncated": total > len(rows), "rows": rows}

    def incidents(self, *, time_from: str | None = None, time_to: str | None = None, limit: int | None = None):
        where, params = ["1=1"], []
        if (t := parse_ts(time_to, end_of_day=True)) is not None:
            where.append("first_ts <= ?")
            params.append(t)
        if (t := parse_ts(time_from)) is not None:
            where.append("last_ts >= ?")
            params.append(t)
        clause = " AND ".join(where)
        total = self._scalar(f"SELECT count(*) FROM incidents WHERE {clause}", params)
        rows = self._rows(
            "SELECT incident_id, title, first_ts, last_ts, status, hosts AS servers, group_ids, "
            "root_group_id, confidence "
            f"FROM incidents WHERE {clause} ORDER BY first_ts LIMIT {_clip(limit)}",
            params,
        )
        for r in rows:
            r["first_ts"], r["last_ts"] = iso(r["first_ts"]), iso(r["last_ts"])
            r["title"] = _short(r["title"])
        return {"total_matches": total, "returned": len(rows), "truncated": total > len(rows), "rows": rows}

    def correlations(self, group_id: int) -> dict[str, Any]:
        group = self._rows(
            "SELECT g.group_id, g.host, g.component, t.template AS title, g.first_ts, g.last_ts, "
            f"g.count AS event_count, g.status FROM error_groups g {self._TEMPLATE_JOIN} "
            "WHERE g.group_id = ?",
            [group_id],
        )
        if not group:
            return {"error": f"No error group with id {group_id}."}
        links = self._rows(
            "SELECT c.kind, c.confidence, c.link_key AS reason, c.lag_s, "
            "CASE WHEN c.group_a = ? THEN 'effect' ELSE 'cause' END AS other_is, "
            "o.group_id AS other_group_id, o.host, o.component, t.template AS title, "
            "o.first_ts, o.last_ts, o.status, "
            "COALESCE((SELECT list(m.event_pk) FROM (SELECT event_pk FROM group_members WHERE group_id = o.group_id "
            "ORDER BY event_pk LIMIT 3) m), list_slice(o.sample_event_ids, 1, 3)) AS sample_event_ids "
            "FROM correlations c JOIN error_groups o ON o.group_id = CASE WHEN c.group_a = ? THEN c.group_b "
            "ELSE c.group_a END LEFT JOIN templates t ON t.template_id = o.template_id "
            "WHERE c.group_a = ? OR c.group_b = ? ORDER BY c.confidence DESC LIMIT 20",
            [group_id, group_id, group_id, group_id],
        )
        for r in links:
            r["first_ts"], r["last_ts"] = iso(r["first_ts"]), iso(r["last_ts"])
            r["title"] = _short(r["title"])
            r["sample_event_ids"] = r["sample_event_ids"] or []
        g = group[0]
        g["first_ts"], g["last_ts"], g["title"] = iso(g["first_ts"]), iso(g["last_ts"]), _short(g["title"])
        return {"group": g, "linked_groups": links, "returned": len(links)}

    # -------------------------------------------------- evidence
    def existing_event_ids(self, ids: list[int]) -> set[int]:
        if not ids:
            return set()
        rows = self.cur.execute("SELECT id FROM events WHERE list_contains(?, id)", [list(ids)]).fetchall()
        return {r[0] for r in rows}

    def evidence_for(self, ids: list[int]) -> list[dict[str, Any]]:
        if not ids:
            return []
        rows = self._rows(
            "SELECT e.id AS event_id, e.host AS server, s.path AS file, e.line_start AS line, e.ts_utc AS ts "
            "FROM events e LEFT JOIN sources s ON s.source_id = e.source_id WHERE list_contains(?, e.id) "
            "ORDER BY e.ts_utc, e.id",
            [list(ids)],
        )
        for r in rows:
            r["ts"] = iso(r["ts"])
        return rows

    # -------------------------------------------------- persistence (best effort)
    def save_message(
        self, conversation_id: str, role: str, content: str, answer: dict[str, Any] | None = None
    ) -> None:
        try:
            self.cur.execute(
                "INSERT INTO chat_messages (message_id, conversation_id, role, content, answer, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                [
                    self._next_id("chat_messages", "message_id"),
                    conversation_id,
                    role,
                    content,
                    json.dumps(answer, ensure_ascii=False) if answer is not None else None,
                    _now(),
                ],
            )
        except duckdb.Error as exc:
            log.warning("could not store chat message: %s", exc)

    def save_hypothesis(
        self, conversation_id: str, question: str, answer: dict[str, Any], model: str | None = None
    ) -> None:
        try:
            self.cur.execute(
                "INSERT INTO hypotheses (hypothesis_id, incident_id, conversation_id, question, answer, "
                "model, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                [
                    self._next_id("hypotheses", "hypothesis_id"),
                    None,
                    conversation_id,
                    question,
                    json.dumps(answer, ensure_ascii=False),
                    model,
                    _now(),
                ],
            )
        except duckdb.Error as exc:
            log.warning("could not store hypothesis: %s", exc)

    def save_llm_call(self, row: dict[str, Any]) -> None:
        try:
            self.cur.execute(
                "INSERT INTO llm_calls (call_id, conversation_id, hypothesis_id, model, input_tokens, "
                "output_tokens, duration_ms, cost_eur, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    self._next_id("llm_calls", "call_id"),
                    row["conversation_id"],
                    None,
                    f"{row['provider']}/{row['model']}",
                    row["input_tokens"],
                    row["output_tokens"],
                    row["duration_ms"],
                    row["cost_eur"],
                    _now(),
                ],
            )
        except duckdb.Error as exc:
            log.warning("could not store llm call: %s", exc)

    def history(self, conversation_id: str, limit: int = 50) -> list[dict[str, Any]]:
        try:
            rows = self._rows(
                "SELECT role, content, created_at FROM chat_messages WHERE conversation_id = ? "
                f"ORDER BY message_id LIMIT {int(limit)}",
                [conversation_id],
            )
        except duckdb.Error:
            return []
        for r in rows:
            r["created_at"] = iso(r["created_at"])
        return rows
