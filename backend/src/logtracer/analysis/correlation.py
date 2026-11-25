"""Correlate error groups using shared job and trace IDs, or time if they have none."""

import duckdb

from logtracer.analysis.problems import atomic

MAX_LAG_S = 300
TRACE_CONFIDENCE = 0.8
JOB_CONFIDENCE = 0.7
# Groups without any ID: neighbours in time are weakly linked (kind "soft").
SOFT_LAG_S = 15
SOFT_CONFIDENCE = 0.6


def build_correlations(con: duckdb.DuckDBPyConnection, max_lag_seconds: int = MAX_LAG_S) -> dict:
    """Rebuild `correlations`: pairs of groups that share a job or trace ID within the time limit.

    One row per pair of groups, however many jobs they share: the strongest key (a trace ID
    before a job ID), the direction in time and the typical lag over all shared keys. A shared
    key is a strong hint, not a proof of cause. Groups whose events carry no ID at all are linked
    to the next such group if it starts within SOFT_LAG_S.
    """
    with atomic(con):
        con.execute("DELETE FROM correlations")
        con.execute(
            """
            INSERT INTO correlations
            WITH keys AS (
                SELECT gm.group_id, e.ts_utc, 'trace_id' AS key_type, trim(e.trace_id) AS key
                FROM group_members gm JOIN events e ON e.id = gm.event_pk
                WHERE e.duplicate_of IS NULL AND trim(coalesce(e.trace_id, '')) <> ''
                UNION ALL
                SELECT gm.group_id, e.ts_utc, 'job_id', trim(e.job_id)
                FROM group_members gm JOIN events e ON e.id = gm.event_pk
                WHERE e.duplicate_of IS NULL AND trim(coalesce(e.job_id, '')) <> ''
            ), firsts AS (
                SELECT group_id, key_type, key, min(ts_utc) AS ts FROM keys
                WHERE ts_utc IS NOT NULL GROUP BY ALL
            ), shared AS (
                SELECT a.group_id AS x, b.group_id AS y, a.key_type, a.key,
                       epoch(b.ts) - epoch(a.ts) AS lag, a.ts
                FROM firsts a JOIN firsts b USING (key_type, key)
                WHERE a.group_id < b.group_id AND abs(epoch(b.ts) - epoch(a.ts)) <= ?
            ), pairs AS (
                SELECT x, y, median(lag) AS lag, bool_or(key_type = 'trace_id') AS by_trace,
                       arg_min(key_type || '=' || key, (key_type = 'job_id', ts, key)) AS link_key
                FROM shared GROUP BY x, y
            ), without_id AS (
                SELECT gm.group_id, min(e.ts_utc) AS ts
                FROM group_members gm JOIN events e ON e.id = gm.event_pk
                GROUP BY gm.group_id
                HAVING bool_and(trim(coalesce(e.trace_id, '')) = ''
                                AND trim(coalesce(e.job_id, '')) = '')
            ), neighbours AS (
                SELECT group_id AS a, ts, lead(group_id) OVER w AS b, lead(ts) OVER w AS next_ts
                FROM without_id WINDOW w AS (ORDER BY ts, group_id)
            ), links AS (
                SELECT CASE WHEN lag >= 0 THEN x ELSE y END AS a,
                       CASE WHEN lag >= 0 THEN y ELSE x END AS b, 'hard' AS kind, link_key,
                       abs(lag) AS lag, CASE WHEN by_trace THEN ? ELSE ? END AS confidence
                FROM pairs
                UNION ALL
                SELECT a, b, 'soft', 'time', epoch(next_ts) - epoch(ts), ?
                FROM neighbours WHERE b IS NOT NULL AND epoch(next_ts) - epoch(ts) <= ?
            )
            SELECT row_number() OVER (ORDER BY a, b), a, b, kind, link_key, lag, confidence
            FROM links
            """,
            [max_lag_seconds, TRACE_CONFIDENCE, JOB_CONFIDENCE, SOFT_CONFIDENCE, SOFT_LAG_S],
        )
    count = con.execute("SELECT count(*) FROM correlations").fetchone()[0]
    return {"candidate_relationships": count, "correlations_inserted": count}
