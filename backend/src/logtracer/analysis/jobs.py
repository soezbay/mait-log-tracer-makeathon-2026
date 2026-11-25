"""Combine events into jobs: what ran when, on which servers, with which result."""

import duckdb

from logtracer.analysis.error_groups import RECOVERED
from logtracer.analysis.problems import atomic, collect_problems

# Without a trace ID a pause this long means another job with the same number.
JOB_GAP = "INTERVAL 30 MINUTE"
# "JOB-2003-R07" is a re-run of "JOB-2003": one job with several runs.
FAMILY = r"regexp_replace(trim(job_id), '-R\d+$', '')"
CONVERSION = r"convert|translator|nx/|nx_|se_jt|se/batch|me10|/pdf|_jt|_pdf"


def build_jobs(con: duckdb.DuckDBPyConnection) -> dict:
    """Rebuild `jobs`.

    A job is a job number within one trace, or, without a trace ID, a job number without a long
    pause. Lines without a trace ID next to the only trace of their job number belong to it. Status from the real problems only (harmless messages do not count):
    recovered (the last problem says so), failed (ERROR or FATAL), warning (only WARN), ok.
    """
    collect_problems(con)
    con.execute(
        f"""
        CREATE OR REPLACE TEMP TABLE job_events AS
        WITH e AS (
            SELECT id, {FAMILY} AS family, nullif(trim(trace_id), '') AS trace, trim(job_id) AS run,
                   host, component, ts_utc
            FROM events
            WHERE duplicate_of IS NULL AND ts_utc IS NOT NULL
              AND trim(coalesce(job_id, '')) <> ''
        ), only_trace AS (
            SELECT family, any_value(trace) AS trace, min(ts_utc) AS a, max(ts_utc) AS b
            FROM e WHERE trace IS NOT NULL GROUP BY family HAVING count(DISTINCT trace) = 1
        ), e2 AS (
            SELECT e.* REPLACE (coalesce(e.trace, o.trace) AS trace)
            FROM e LEFT JOIN only_trace o ON o.family = e.family
                AND e.ts_utc BETWEEN o.a - {JOB_GAP} AND o.b + {JOB_GAP}
        ), marked AS (
            SELECT *, trace IS NULL AND ts_utc - lag(ts_utc) OVER w > {JOB_GAP} AS after_pause
            FROM e2 WINDOW w AS (PARTITION BY family, trace ORDER BY ts_utc, id)
        ), numbered AS (
            SELECT *, count(*) FILTER (WHERE after_pause) OVER w AS part
            FROM marked WINDOW w AS (PARTITION BY family, trace ORDER BY ts_utc, id)
        )
        SELECT *, first_value(id) OVER (
            PARTITION BY family, trace, part ORDER BY ts_utc, id
        ) AS job_pk
        FROM numbered
        """
    )
    with atomic(con):
        con.execute("DELETE FROM jobs")
        con.execute(
            """
            INSERT INTO jobs
            WITH problems AS (
                SELECT j.job_pk, p.id, p.ts_utc, p.level, p.message,
                       regexp_matches(p.message, $recovered, 'i') AS recovered
                FROM problem_events p JOIN job_events j USING (id)
            ), incident_of AS (
                SELECT m.event_pk AS id, i.incident_id
                FROM (SELECT incident_id, unnest(group_ids) AS group_id FROM incidents) i
                JOIN group_members m USING (group_id)
            ), summary AS (
                SELECT job_pk,
                       count(*) FILTER (WHERE level IN ('ERROR', 'FATAL')) AS errors,
                       count(*) FILTER (WHERE level = 'WARN') AS warnings,
                       arg_max(recovered, (ts_utc, p.id)) AS ends_recovered,
                       -- the first error, else the first warning
                       arg_min(p.id, (level = 'WARN', ts_utc, p.id)) AS problem_event_id,
                       arg_min(message, (level = 'WARN', ts_utc, p.id)) AS problem,
                       min(incident_id) AS incident_id
                FROM problems p LEFT JOIN incident_of USING (id)
                GROUP BY job_pk
            ), base AS (
                SELECT job_pk, any_value(family) AS job_id, any_value(trace) AS trace_id,
                       count(DISTINCT run) AS runs, min(ts_utc) AS first_ts, max(ts_utc) AS last_ts,
                       list(DISTINCT host ORDER BY host) FILTER (WHERE host IS NOT NULL) AS hosts,
                       count(*) AS events,
                       bool_or(coalesce(regexp_matches(component, $conversion, 'i'), FALSE))
                           AS conversion
                FROM job_events GROUP BY job_pk
            )
            SELECT b.job_pk, b.job_id, b.trace_id, b.runs,
                   CASE WHEN s.job_pk IS NULL THEN 'ok' WHEN s.ends_recovered THEN 'recovered'
                        WHEN s.errors > 0 THEN 'failed' ELSE 'warning' END,
                   b.first_ts, b.last_ts, coalesce(b.hosts, []), b.events,
                   coalesce(s.errors, 0), coalesce(s.warnings, 0), s.problem_event_id, s.problem,
                   b.conversion, s.incident_id
            FROM base b LEFT JOIN summary s USING (job_pk)
            """,
            {"recovered": RECOVERED, "conversion": CONVERSION},
        )
    return {"jobs_created": con.execute("SELECT count(*) FROM jobs").fetchone()[0]}
