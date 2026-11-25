
"""Detect unusual spikes in log error counts."""

from statistics import mean, pstdev


def detect_spikes(counts, min_errors=5, sensitivity=3.0):
    """
    Find unusually high error counts.

    counts: list of error counts per time interval
    min_errors: minimum number of errors to flag
    sensitivity: number of standard deviations above baseline
    """

    if not counts:
        return []

    baseline = mean(counts)
    deviation = pstdev(counts)

    threshold = max(
        min_errors,
        baseline + sensitivity * deviation
    )

    anomalies = []

    for index, count in enumerate(counts):
        if count > threshold:
            anomalies.append({
                "index": index,
                "count": count,
                "threshold": round(threshold, 2),
                "kind": "rate_spike"
            })

    return anomalies



"""Database-backed rate spike detection."""

import json
from collections import defaultdict
from datetime import timedelta


def build_anomalies(
    con,
    baseline_windows=5,
    min_errors=5,
    multiplier=3.0,
):
    """Detect error spikes using earlier observed minutes."""

    rows = con.execute("""
        SELECT
            COALESCE(host, 'unknown') AS host,
            COALESCE(component, 'unknown') AS component,
            DATE_TRUNC('minute', ts_utc) AS minute,
            COUNT(*) AS errors
        FROM events
        WHERE UPPER(TRIM(level)) IN
              ('ERROR', 'FATAL', 'CRITICAL')
          AND duplicate_of IS NULL
          AND ts_utc IS NOT NULL
        GROUP BY 1, 2, 3
        ORDER BY 1, 2, 3
    """).fetchall()

    series = defaultdict(list)

    for host, component, minute, count in rows:
        series[(host, component)].append((minute, count))

    found = []

    for (host, component), values in series.items():
        # Identify high-volume bursts without sufficient history.
        for minute, count in values[:baseline_windows]:
            if count < 30:
                continue

            details = {
                "observed_errors": count,
                "threshold": 30,
                "baseline_average": None,
                "baseline_type": "cold_start_burst",
                "note": "High error volume without enough baseline history",
            }

            found.append((
                host,
                component,
                minute,
                minute + timedelta(minutes=1),
                round(count / 30, 2),
                json.dumps(details),
            ))
        for i in range(baseline_windows, len(values)):
            previous = values[i - baseline_windows:i]

            baseline = sum(item[1] for item in previous)
            baseline /= baseline_windows

            minute, count = values[i]

            threshold = max(
                min_errors,
                baseline * multiplier
            )

            if count <= threshold:
                continue

            score = count / max(baseline, 1.0)

            details = {
                "observed_errors": count,
                "baseline_average": baseline,
                "threshold": threshold,
                "baseline_type": "previous_observed_minutes"
            }

            found.append((
                host,
                component,
                minute,
                minute + timedelta(minutes=1),
                score,
                json.dumps(details)
            ))

    # Append new detections without deleting existing ones.
    # The caller must coordinate database writes with P1.
    con.execute("BEGIN TRANSACTION")

    try:
        next_id = con.execute("""
            SELECT COALESCE(MAX(anomaly_id), 0) + 1
            FROM anomalies
        """).fetchone()[0]

        inserted = 0

        for host, component, start, end, score, details in found:
            exists = con.execute("""
                SELECT COUNT(*)
                FROM anomalies
                WHERE host = ?
                  AND component = ?
                  AND kind = 'rate_spike'
                  AND window_start = ?
            """, [host, component, start]).fetchone()[0]

            if exists:
                continue

            con.execute("""
                INSERT INTO anomalies (
                    anomaly_id,
                    host,
                    component,
                    kind,
                    window_start,
                    window_end,
                    score,
                    details
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, [
                next_id,
                host,
                component,
                "rate_spike",
                start,
                end,
                score,
                details
            ])

            next_id += 1
            inserted += 1

        con.execute("COMMIT")

    except Exception:
        con.execute("ROLLBACK")
        raise

    return {
        "anomalies_detected": len(found),
        "anomalies_inserted": inserted
    }
