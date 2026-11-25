"""Classify log messages by severity and group the problem events."""

import duckdb

from logtracer.analysis.problems import atomic, collect_problems

ERROR_LEVELS = {"ERROR", "FATAL", "CRITICAL"}
WARNING_LEVELS = {"WARN", "WARNING"}

# A group ends when its message is silent for this long on its server and component.
GROUP_GAP = "INTERVAL 2 HOUR"
SAMPLES = 10
RECOVERED = r"\b(recovered|retry (completed|succeeded|successful)|completed successfully)\b"


def classify_event(level, message):
    """Classify a log event using its recorded severity."""

    level = (level or "").upper().strip()
    message = (message or "").lower()

    if level in ERROR_LEVELS:
        return "error"

    if level in WARNING_LEVELS:
        return "warning"

    if level in {"INFO", "DEBUG", "TRACE"}:
        return "normal"

    # For unknown levels, use a limited fallback.
    failure_words = (
        "connection failed",
        "connection timeout",
        "permission denied",
        "database unavailable",
    )

    if any(word in message for word in failure_words):
        return "possible_error"

    return "unknown"


def build_error_groups(con: duckdb.DuckDBPyConnection) -> dict:
    """Rebuild `error_groups` and `group_members` from the problem events.

    A group is one message on one server and component without a long pause. Its ID is the ID
    of its first event, so it stays the same when the analysis runs again.

    Status: recovered (the message says so), failed (ERROR or FATAL), otherwise unknown.
    """
    events = collect_problems(con)
    con.execute(
        f"""
        CREATE OR REPLACE TEMP TABLE grouped_events AS
        WITH marked AS (
            SELECT *, ts_utc - lag(ts_utc) OVER w > {GROUP_GAP} AS after_pause
            FROM problem_events
            WINDOW w AS (PARTITION BY message_key, host, component ORDER BY ts_utc, id)
        ), numbered AS (
            SELECT *, count(*) FILTER (WHERE after_pause) OVER w AS part
            FROM marked
            WINDOW w AS (PARTITION BY message_key, host, component ORDER BY ts_utc, id)
        )
        SELECT *, first_value(id) OVER (
            PARTITION BY message_key, host, component, part ORDER BY ts_utc, id
        ) AS group_id
        FROM numbered
        """
    )
    with atomic(con):
        con.execute("DELETE FROM group_members")
        con.execute("DELETE FROM error_groups")
        con.execute("INSERT INTO group_members SELECT group_id, id FROM grouped_events")
        con.execute(
            f"""
            INSERT INTO error_groups
            SELECT group_id, mode(template_id), coalesce(any_value(host), 'unknown'),
                   coalesce(any_value(component), 'unknown'),
                   arg_max(level, CASE level WHEN 'FATAL' THEN 3 WHEN 'ERROR' THEN 2 ELSE 1 END),
                   count(*), min(ts_utc), max(ts_utc),
                   CASE WHEN bool_and(regexp_matches(message, ?, 'i')) THEN 'recovered'
                        WHEN bool_or(level IN ('ERROR', 'FATAL')) THEN 'failed'
                        ELSE 'unknown' END,
                   list(id ORDER BY ts_utc, id)[1:{SAMPLES}]
            FROM grouped_events GROUP BY group_id
            """,
            [RECOVERED],
        )
    groups = con.execute("SELECT count(*) FROM error_groups").fetchone()[0]
    return {"events_processed": events, "groups_created": groups}
