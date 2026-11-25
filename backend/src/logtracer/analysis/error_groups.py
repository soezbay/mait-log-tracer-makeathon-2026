"""Classify log messages by severity."""

ERROR_LEVELS = {"ERROR", "FATAL", "CRITICAL"}
WARNING_LEVELS = {"WARN", "WARNING"}


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



def build_error_groups(con):
    """Group warning and error events in DuckDB."""

    rows = con.execute("""
        SELECT
            id,
            template_id,
            host,
            component,
            level,
            ts_utc
        FROM events
        WHERE UPPER(TRIM(level)) IN (
            'WARN', 'WARNING', 'ERROR',
            'FATAL', 'CRITICAL'
        )
        AND duplicate_of IS NULL
        ORDER BY ts_utc, id
    """).fetchall()

    groups = {}

    for event_id, template_id, host, component, level, timestamp in rows:

        key = (
            template_id,
            host or "unknown",
            component or "unknown"
        )

        if key not in groups:
            groups[key] = {
                "level": level.upper(),
                "count": 0,
                "timestamps": [],
                "event_ids": []
            }

        group = groups[key]
        group["count"] += 1
        group["event_ids"].append(event_id)

        if timestamp is not None:
            group["timestamps"].append(timestamp)

        severity = {
            "WARN": 1,
            "WARNING": 1,
            "ERROR": 2,
            "FATAL": 3,
            "CRITICAL": 3
        }

        if severity.get(level.upper(), 0) > severity.get(
            group["level"], 0
        ):
            group["level"] = level.upper()

    # Only rebuild P2 grouping tables.
    # Use an isolated database during testing.
    con.execute("BEGIN TRANSACTION")

    try:
        con.execute("DELETE FROM group_members")
        con.execute("DELETE FROM error_groups")

        for group_id, (key, group) in enumerate(
            groups.items(), start=1
        ):
            template_id, host, component = key
            times = group["timestamps"]

            con.execute("""
                INSERT INTO error_groups (
                    group_id,
                    template_id,
                    host,
                    component,
                    level,
                    count,
                    first_ts,
                    last_ts,
                    status,
                    sample_event_ids
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, [
                group_id,
                template_id,
                host,
                component,
                group["level"],
                group["count"],
                min(times) if times else None,
                max(times) if times else None,
                "unknown",
                group["event_ids"][:10]
            ])

            con.executemany("""
                INSERT INTO group_members (
                    group_id, event_pk
                )
                VALUES (?, ?)
            """, [
                (group_id, event_id)
                for event_id in group["event_ids"]
            ])

        con.execute("COMMIT")

    except Exception:
        con.execute("ROLLBACK")
        raise

    return {
        "events_processed": len(rows),
        "groups_created": len(groups)
    }
