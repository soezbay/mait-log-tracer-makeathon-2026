
"""Correlate error groups using shared job and trace IDs."""

from collections import defaultdict


def build_correlations(con, max_lag_seconds=300):
    """
    Find possible relationships between error groups.

    Uses:
    - Shared job_id or trace_id
    - Event timestamps
    - Different error group IDs

    Receives Safak's existing DuckDB connection.
    """

    rows = con.execute("""
        SELECT
            gm.group_id,
            e.host,
            e.ts_utc,
            e.job_id,
            e.trace_id
        FROM group_members gm
        JOIN events e ON e.id = gm.event_pk
        WHERE e.duplicate_of IS NULL
          AND e.ts_utc IS NOT NULL
          AND (
              NULLIF(TRIM(e.job_id), '') IS NOT NULL
              OR NULLIF(TRIM(e.trace_id), '') IS NOT NULL
          )
    """).fetchall()

    linked = defaultdict(dict)

    for group_id, host, timestamp, job_id, trace_id in rows:
        identifiers = []

        if job_id and job_id.strip():
            identifiers.append(("job_id", job_id.strip()))

        if trace_id and trace_id.strip():
            identifiers.append(("trace_id", trace_id.strip()))

        for identifier in identifiers:
            # Keep earliest timestamp per group and identifier.
            existing = linked[identifier].get(group_id)

            if existing is None or timestamp < existing[0]:
                linked[identifier][group_id] = (
                    timestamp, host
                )

    candidates = {}

    for (key_type, key_value), groups in linked.items():
        ordered = []

        for group_id, (timestamp, host) in groups.items():
            ordered.append((timestamp, group_id, host))

        ordered.sort()

        for index, (time_a, group_a, host_a) in enumerate(ordered):
            for time_b, group_b, host_b in ordered[index + 1:]:
                lag = (time_b - time_a).total_seconds()

                if lag > max_lag_seconds:
                    break

                if group_a == group_b:
                    continue

                # Strong identifier match, but not causal proof.
                pair = (group_a, group_b, key_type, key_value)

                candidates[pair] = (
                    lag,
                    0.8 if key_type == "trace_id" else 0.7
                )

    inserted = 0

    con.execute("BEGIN TRANSACTION")

    try:
        row = con.execute("""
            SELECT COALESCE(MAX(correlation_id), 0) + 1
            FROM correlations
        """).fetchone()

        next_id = row[0]

        for (group_a, group_b, key_type, key_value), (
            lag, confidence
        ) in candidates.items():

            link_key = f"{key_type}={key_value}"

            existing = con.execute("""
                SELECT COUNT(*)
                FROM correlations
                WHERE group_a = ?
                  AND group_b = ?
                  AND link_key = ?
            """, [group_a, group_b, link_key]).fetchone()[0]

            if existing:
                continue

            con.execute("""
                INSERT INTO correlations (
                    correlation_id,
                    group_a,
                    group_b,
                    kind,
                    link_key,
                    lag_s,
                    confidence
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, [
                next_id,
                group_a,
                group_b,
                "hard",
                link_key,
                lag,
                confidence
            ])

            next_id += 1
            inserted += 1

        con.execute("COMMIT")

    except Exception:
        con.execute("ROLLBACK")
        raise

    return {
        "candidate_relationships": len(candidates),
        "correlations_inserted": inserted
    }
