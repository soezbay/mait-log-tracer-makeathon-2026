"""SQL for reading the analysis tables (incidents, error groups, anomalies)."""

import json

import duckdb

# "JOB-2003-R07" is a re-run of "JOB-2003".
JOB_FAMILY = r"regexp_replace(e.job_id, '-R\d+$', '')"


def _rows(con: duckdb.DuckDBPyConnection, sql: str, params: list | None = None) -> list[dict]:
    result = con.execute(sql, params or [])
    columns = [c[0] for c in result.description]
    return [dict(zip(columns, row, strict=True)) for row in result.fetchall()]


def table_counts(con: duckdb.DuckDBPyConnection) -> dict[str, int]:
    tables = ("events", "error_groups", "anomalies", "correlations", "incidents")
    return {t: con.execute(f"SELECT count(*) FROM {t}").fetchone()[0] for t in tables}


def _time_filter(where: list[str], params: list, first: str, last: str, ts_from, ts_to) -> None:
    """Keep rows whose period overlaps ts_from … ts_to."""
    if ts_from is not None:
        where.append(f"{last} >= ?")
        params.append(ts_from)
    if ts_to is not None:
        where.append(f"{first} <= ?")
        params.append(ts_to)


_INCIDENT_COLUMNS = """
    i.incident_id, i.title, i.first_ts, i.last_ts, i.status, i.hosts, i.confidence,
    len(i.group_ids) AS group_count,
    (SELECT sum(g.count) FROM error_groups g WHERE list_contains(i.group_ids, g.group_id))
        AS event_count,
    r.host AS root_host, r.component AS root_component, r.level AS root_level,
    r.sample_event_ids[1] AS root_event_id
"""


def list_incidents(
    con: duckdb.DuckDBPyConnection,
    *,
    incident_id: int | None = None,
    event_id: int | None = None,
    server: str | None = None,
    status: str | None = None,
    q: str | None = None,
    ts_from=None,
    ts_to=None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[dict], int]:
    """Incidents, newest first."""
    where, params = [], []
    if incident_id is not None:
        where.append("i.incident_id = ?")
        params.append(incident_id)
    if event_id is not None:
        # A duplicate line belongs to the incident of its original.
        where.append(
            "EXISTS (SELECT 1 FROM group_members m WHERE list_contains(i.group_ids, m.group_id) "
            "AND m.event_pk = (SELECT coalesce(duplicate_of, id) FROM events WHERE id = ?))")
        params.append(event_id)
    if server:
        where.append("list_contains(i.hosts, ?)")
        params.append(server)
    if status:
        where.append("i.status = ?")
        params.append(status)
    if q:
        where.append(
            "(i.title ILIKE ? OR EXISTS (SELECT 1 FROM group_members m "
            "JOIN events e ON e.id = m.event_pk WHERE list_contains(i.group_ids, m.group_id) "
            "AND (e.job_id ILIKE ? OR e.message ILIKE ?)))")
        params += [f"%{q}%"] * 3
    _time_filter(where, params, "i.first_ts", "i.last_ts", ts_from, ts_to)
    clause = f"WHERE {' AND '.join(where)}" if where else ""
    total = con.execute(f"SELECT count(*) FROM incidents i {clause}", params).fetchone()[0]
    items = _rows(
        con,
        f"""
        SELECT {_INCIDENT_COLUMNS}
        FROM incidents i LEFT JOIN error_groups r ON r.group_id = i.root_group_id
        {clause} ORDER BY i.first_ts DESC NULLS LAST, i.incident_id LIMIT ? OFFSET ?
        """,
        [*params, limit, offset],
    )
    return items, total


def incident_jobs(con: duckdb.DuckDBPyConnection, incident_ids: list[int]
                  ) -> dict[int, list[dict]]:
    """incident -> its jobs with the number of runs (JOB-2003 and JOB-2003-R01 are one job)."""
    rows = _rows(
        con,
        f"""
        SELECT i.incident_id, {JOB_FAMILY} AS job_id, count(DISTINCT e.job_id) AS runs
        FROM incidents i
        JOIN group_members m ON list_contains(i.group_ids, m.group_id)
        JOIN events e ON e.id = m.event_pk
        WHERE list_contains(?, i.incident_id) AND trim(coalesce(e.job_id, '')) <> ''
        GROUP BY ALL ORDER BY runs DESC, job_id
        """,
        [incident_ids],
    )
    jobs: dict[int, list[dict]] = {}
    for row in rows:
        jobs.setdefault(row.pop("incident_id"), []).append(row)
    return jobs


def incident_group_ids(con: duckdb.DuckDBPyConnection, incident_id: int
                       ) -> tuple[list[int], int] | None:
    """(group IDs, trigger group) of an incident."""
    return con.execute(
        "SELECT group_ids, root_group_id FROM incidents WHERE incident_id = ?", [incident_id]
    ).fetchone()


def groups(con: duckdb.DuckDBPyConnection, *, group_ids: list[int] | None = None,
           limit: int = 500, offset: int = 0) -> tuple[list[dict], int]:
    """Error groups in time order with their first log line."""
    where, params = "", []
    if group_ids is not None:
        where, params = "WHERE list_contains(?, g.group_id)", [group_ids]
    total = con.execute(f"SELECT count(*) FROM error_groups g {where}", params).fetchone()[0]
    items = _rows(
        con,
        f"""
        SELECT g.group_id, g.host, g.component, g.level, g.status, g.count, g.first_ts, g.last_ts,
               g.sample_event_ids AS event_ids, e.id AS event_id, e.message, e.job_id, e.trace_id,
               e.clock_offset_s, s.path AS source_path, e.line_start, e.line_end
        FROM error_groups g
        LEFT JOIN events e ON e.id = g.sample_event_ids[1]
        LEFT JOIN sources s ON s.source_id = e.source_id
        {where} ORDER BY g.first_ts, g.group_id LIMIT ? OFFSET ?
        """,
        [*params, limit, offset],
    )
    return items, total


def links(con: duckdb.DuckDBPyConnection, group_ids: list[int]) -> list[dict]:
    return _rows(
        con,
        """
        SELECT group_a, group_b, kind, link_key, lag_s, confidence FROM correlations
        WHERE list_contains(?, group_a) AND list_contains(?, group_b)
        ORDER BY correlation_id
        """,
        [group_ids, group_ids],
    )


def list_anomalies(con: duckdb.DuckDBPyConnection, *, server: str | None = None,
                   hosts: list[str] | None = None, ts_from=None, ts_to=None, limit: int = 50,
                   offset: int = 0) -> tuple[list[dict], int]:
    """Anomalies, newest first."""
    where, params = [], []
    if server:
        where.append("host = ?")
        params.append(server)
    if hosts is not None:
        where.append("list_contains(?, host)")
        params.append(hosts)
    _time_filter(where, params, "window_start", "window_end", ts_from, ts_to)
    clause = f"WHERE {' AND '.join(where)}" if where else ""
    total = con.execute(f"SELECT count(*) FROM anomalies {clause}", params).fetchone()[0]
    items = _rows(
        con,
        f"""
        SELECT anomaly_id, host, component, kind, window_start, window_end, score,
               CAST(details AS VARCHAR) AS details
        FROM anomalies {clause}
        ORDER BY window_start DESC, anomaly_id LIMIT ? OFFSET ?
        """,
        [*params, limit, offset],
    )
    for item in items:
        item["details"] = json.loads(item["details"]) if item["details"] else {}
    return items, total
