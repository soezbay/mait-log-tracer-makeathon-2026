"""SQL behind the question suggestions for the assistant (GET /api/suggestions).

Not every ERROR line is a problem: in the log package messages like "Cache lookup successful"
are logged as ERROR now and then and as INFO thousands of times. A message counts as a real
("signal") error only if at least NOISE_SHARE of all its lines are ERROR or FATAL.
"""

from datetime import datetime

import duckdb

NOISE_SHARE = 0.10

_ERROR = "level IN ('ERROR', 'FATAL')"


def _family(value: str) -> str:
    """SQL for the job without its run suffix: JOB-2003-R07 is a re-run of JOB-2003."""
    return rf"regexp_replace({value}, '-R\d+$', '')"


def _rows(con: duckdb.DuckDBPyConnection, sql: str, params: list | None = None) -> list[dict]:
    result = con.execute(sql, params or [])
    columns = [c[0] for c in result.description]
    return [dict(zip(columns, row, strict=True)) for row in result.fetchall()]


def prepare(con: duckdb.DuckDBPyConnection) -> None:
    """Collect all error events with their message's error share in a temp table.

    Temp tables are private to the cursor, so requests do not see each other's data.
    """
    con.execute(
        rf"""
        CREATE OR REPLACE TEMP TABLE suggestion_errors AS
        WITH errors AS (
            SELECT id, ts_utc, host, component, job_id, message FROM events
            WHERE {_ERROR} AND duplicate_of IS NULL AND ts_utc IS NOT NULL
              AND message IS NOT NULL
        ), shares AS (
            SELECT message, avg(CASE WHEN {_ERROR} THEN 1.0 ELSE 0.0 END) AS error_share
            FROM events
            WHERE duplicate_of IS NULL AND message IN (SELECT message FROM errors)
            GROUP BY message
        )
        SELECT errors.*, {_family('job_id')} AS family, shares.error_share >= ? AS is_signal,
               regexp_extract(message, '\bINC-\d+\b') AS incident
        FROM errors JOIN shares USING (message)
        """,
        [NOISE_SHARE],
    )


def newest_error(con: duckdb.DuckDBPyConnection) -> datetime | None:
    return con.execute("SELECT max(ts_utc) FROM suggestion_errors WHERE is_signal").fetchone()[0]


def job_families(con: duckdb.DuckDBPyConnection, since: datetime, limit: int) -> list[dict]:
    """Jobs (re-runs counted with their job) with errors since `since`, widest spread first."""
    return _rows(
        con,
        """
        SELECT coalesce(min(job_id) FILTER (WHERE job_id = family), min(job_id)) AS job_id,
               count(*) AS errors, count(DISTINCT job_id) AS runs, count(DISTINCT host) AS servers,
               max(ts_utc) AS last_ts, arg_max(id, ts_utc) AS event_id
        FROM suggestion_errors
        WHERE is_signal AND family <> '' AND ts_utc >= ?
        GROUP BY family
        ORDER BY servers DESC, errors DESC, last_ts DESC, family LIMIT ?
        """,
        [since, limit],
    )


def incidents(con: duckdb.DuckDBPyConnection, limit: int) -> list[dict]:
    """Incident numbers named in error messages (INC-03), newest first."""
    return _rows(
        con,
        """
        SELECT incident, count(*) AS errors, count(DISTINCT host) AS servers,
               max(ts_utc) AS last_ts, arg_max(id, ts_utc) AS event_id
        FROM suggestion_errors WHERE is_signal AND incident <> ''
        GROUP BY incident ORDER BY last_ts DESC, incident LIMIT ?
        """,
        [limit],
    )


def errors_per_day(con: duckdb.DuckDBPyConnection) -> list[dict]:
    """Real errors per day, including days that have logs but no real errors."""
    return _rows(
        con,
        """
        SELECT day, coalesce(errors, 0) AS errors, last_ts, event_id
        FROM (SELECT DISTINCT CAST(ts_utc AS DATE) AS day FROM events WHERE ts_utc IS NOT NULL)
        LEFT JOIN (
            SELECT CAST(ts_utc AS DATE) AS day, count(*) AS errors, max(ts_utc) AS last_ts,
                   arg_max(id, ts_utc) AS event_id
            FROM suggestion_errors WHERE is_signal GROUP BY ALL
        ) USING (day)
        ORDER BY day
        """,
    )


def servers(con: duckdb.DuckDBPyConnection, since: datetime, limit: int) -> list[dict]:
    return _rows(
        con,
        """
        SELECT host, count(*) AS errors, max(ts_utc) AS last_ts, arg_max(id, ts_utc) AS event_id
        FROM suggestion_errors WHERE is_signal AND ts_utc >= ? AND host IS NOT NULL
        GROUP BY host ORDER BY errors DESC, host LIMIT ?
        """,
        [since, limit],
    )


def messages(con: duckdb.DuckDBPyConnection, before: datetime, limit: int) -> list[dict]:
    """Frequent error messages outside the recent window (older problems)."""
    return _rows(
        con,
        """
        SELECT message, count(*) AS errors, count(DISTINCT host) AS servers,
               max(ts_utc) AS last_ts, arg_max(id, ts_utc) AS event_id
        FROM suggestion_errors WHERE is_signal AND incident = '' AND ts_utc < ?
        GROUP BY message ORDER BY errors DESC, message LIMIT ?
        """,
        [before, limit],
    )


def noise(con: duckdb.DuckDBPyConnection, limit: int) -> list[dict]:
    """Messages logged as ERROR now and then that are normal most of the time."""
    return _rows(
        con,
        """
        SELECT message, count(*) AS errors, count(DISTINCT host) AS servers,
               max(ts_utc) AS last_ts, arg_max(id, ts_utc) AS event_id
        FROM suggestion_errors WHERE NOT is_signal
        GROUP BY message ORDER BY errors DESC, message LIMIT ?
        """,
        [limit],
    )


def job_summary(con: duckdb.DuckDBPyConnection, job_id: str) -> dict:
    """Real errors and servers of exactly this job, plus the number of runs of its family."""
    return _rows(
        con,
        f"""
        WITH family AS (
            SELECT job_id, host, level, message FROM events
            WHERE duplicate_of IS NULL AND job_id IS NOT NULL
              AND {_family('job_id')} = {_family('?')}
        ), noise AS (
            SELECT message FROM events
            WHERE duplicate_of IS NULL
              AND message IN (SELECT message FROM family WHERE job_id = ? AND {_ERROR})
            GROUP BY message HAVING avg(CASE WHEN {_ERROR} THEN 1.0 ELSE 0.0 END) < ?
        )
        SELECT count(*) FILTER (WHERE job_id = ? AND {_ERROR}
                   AND message NOT IN (SELECT message FROM noise)) AS errors,
               count(DISTINCT host) FILTER (WHERE job_id = ?) AS servers,
               count(DISTINCT job_id) AS runs,
               {_family('?')} AS family
        FROM family
        """,
        [job_id, job_id, NOISE_SHARE, job_id, job_id, job_id],
    )[0]


def is_noise(con: duckdb.DuckDBPyConnection, message: str) -> bool:
    """True if the message is an error in fewer than NOISE_SHARE of its lines."""
    share = con.execute(
        f"SELECT avg(CASE WHEN {_ERROR} THEN 1.0 ELSE 0.0 END) FROM events "
        "WHERE duplicate_of IS NULL AND message = ?",
        [message],
    ).fetchone()[0]
    return share is not None and share < NOISE_SHARE
