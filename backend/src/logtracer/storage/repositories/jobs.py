"""SQL for the `jobs` table."""

import duckdb

from logtracer.storage.repositories import events as events_repo

# Problems first; newest first within a status.
SORTS = {
    "problems": "CASE status WHEN 'failed' THEN 0 WHEN 'warning' THEN 1 WHEN 'recovered' THEN 2 "
                "ELSE 3 END, last_ts DESC",
    "recent": "last_ts DESC",
    "oldest": "first_ts",
    "duration": "last_ts - first_ts DESC",
    "errors": "errors DESC, warnings DESC, last_ts DESC",
    "job": "job_id, first_ts",
}
COLUMNS = (
    "job_pk", "job_id", "trace_id", "runs", "status", "first_ts", "last_ts", "hosts", "events",
    "errors", "warnings", "problem_event_id", "problem", "conversion", "incident_id",
)


def _rows(con: duckdb.DuckDBPyConnection, sql: str, params: list) -> list[dict]:
    return [dict(zip(COLUMNS, row, strict=True)) for row in con.execute(sql, params).fetchall()]


def search(
    con: duckdb.DuckDBPyConnection,
    *,
    status: str | None = None,
    server: str | None = None,
    q: str | None = None,
    conversion: bool = False,
    ts_from=None,
    ts_to=None,
    sort: str = "problems",
    limit: int = 25,
    offset: int = 0,
) -> tuple[list[dict], int, dict[str, int]]:
    """Returns (jobs, total, number of jobs per status without the status filter)."""
    where, params = [], []
    if server:
        where.append("list_contains(hosts, ?)")
        params.append(server)
    if q:
        where.append("(job_id ILIKE ? OR trace_id ILIKE ? OR problem ILIKE ?)")
        params += [f"%{q.strip()}%"] * 3
    if conversion:
        where.append("conversion")
    if ts_from is not None:
        where.append("last_ts >= ?")
        params.append(ts_from)
    if ts_to is not None:
        where.append("first_ts <= ?")
        params.append(ts_to)
    clause = f"WHERE {' AND '.join(where)}" if where else ""
    by_status = dict(con.execute(
        f"SELECT status, count(*) FROM jobs {clause} GROUP BY status", params).fetchall())
    if status:
        clause += (" AND " if where else "WHERE ") + "status = ?"
        params.append(status)
    total = by_status.get(status, 0) if status else sum(by_status.values())
    items = _rows(
        con,
        f"SELECT {', '.join(COLUMNS)} FROM jobs {clause} "
        f"ORDER BY {SORTS[sort]}, job_pk LIMIT ? OFFSET ?",
        [*params, limit, offset],
    )
    return items, total, by_status


def get(con: duckdb.DuckDBPyConnection, job_pk: int) -> dict | None:
    items = _rows(con, f"SELECT {', '.join(COLUMNS)} FROM jobs WHERE job_pk = ?", [job_pk])
    return items[0] if items else None


def events(con: duckdb.DuckDBPyConnection, job: dict, *, errors_only: bool = False,
           limit: int = 50, offset: int = 0) -> tuple[list[dict], int]:
    """The events of a job in time order."""
    family = r"regexp_replace(trim({}), '-R\d+$', '') = ?"
    # like analysis/jobs.py: lines without a trace ID belong to the only trace of the job number
    traces = f"(SELECT count(DISTINCT trace_id) FROM events WHERE {family.format('job_id')})"
    where = [
        "e.duplicate_of IS NULL",
        "e.ts_utc BETWEEN ? AND ?",
        family.format("e.job_id"),
        ("(nullif(trim(e.trace_id), '') IS NOT DISTINCT FROM ? "
         f"OR (e.trace_id IS NULL AND {traces} = 1))"),
    ]
    params = [job["first_ts"], job["last_ts"], job["job_id"], job["trace_id"], job["job_id"]]
    if errors_only:
        where.append("e.level IN ('WARN', 'ERROR', 'FATAL')")
    return events_repo.select_where(con, " AND ".join(where), params, limit, offset)


def server_names(con: duckdb.DuckDBPyConnection) -> list[str]:
    return [row[0] for row in con.execute("SELECT server FROM servers ORDER BY server").fetchall()]
