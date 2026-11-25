"""Detect unusual spikes in log error counts."""

import json
from collections import defaultdict
from datetime import datetime, timedelta
from statistics import mean, pstdev

import duckdb

from logtracer.analysis.problems import atomic, collect_problems

WINDOW = timedelta(minutes=10)
BASELINE_WINDOWS = 144  # the 24 hours before, windows without errors count as 0
MIN_ERRORS = 5
SENSITIVITY = 3.0  # standard deviations above the baseline
MERGE_GAP = timedelta(minutes=30)  # spikes this close together are one anomaly


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


def build_anomalies(con: duckdb.DuckDBPyConnection, min_errors: int = MIN_ERRORS,
                    sensitivity: float = SENSITIVITY) -> dict:
    """Rebuild `anomalies`: unusually many real errors per server and component.

    Compared are 10-minute windows with the 24 hours before; windows without errors count as 0.
    A rate that stays high becomes the new normal after some hours. score = highest window /
    threshold, so 1 is just unusual.
    """
    collect_problems(con)
    rows = con.execute(
        """
        SELECT coalesce(host, 'unknown'), coalesce(component, 'unknown'),
               time_bucket(INTERVAL 10 MINUTE, ts_utc) AS window_start, count(*)
        FROM problem_events WHERE level IN ('ERROR', 'FATAL')
        GROUP BY ALL ORDER BY ALL
        """
    ).fetchall()
    series: dict[tuple[str, str], dict[datetime, int]] = defaultdict(dict)
    for host, component, start, count in rows:
        series[(host, component)][start] = count

    found = []
    for (host, component), windows in series.items():
        found += [(host, component, *spike) for spike in _spikes(windows, min_errors, sensitivity)]
    found.sort(key=lambda a: (a[2], a[0], a[1]))

    with atomic(con):
        con.execute("DELETE FROM anomalies")
        if found:
            con.executemany(
                "INSERT INTO anomalies VALUES (?, ?, ?, 'rate_spike', ?, ?, ?, ?)",
                [(i, host, component, start, end, score, json.dumps(details))
                 for i, (host, component, start, end, score, details) in enumerate(found, 1)],
            )
    return {"anomalies_detected": len(found), "anomalies_inserted": len(found)}


def _spikes(windows: dict[datetime, int], min_errors: int, sensitivity: float
            ) -> list[tuple[datetime, datetime, float, dict]]:
    history: dict[datetime, int] = {}
    spikes: list[dict] = []
    for start, count in sorted(windows.items()):
        recent = [c for t, c in history.items() if start - WINDOW * BASELINE_WINDOWS <= t]
        counts = recent + [0] * (BASELINE_WINDOWS - len(recent))
        threshold = max(min_errors, mean(counts) + sensitivity * pstdev(counts))
        history[start] = count
        if count < threshold:
            continue
        last = spikes[-1] if spikes else None
        if last and start - last["end"] <= MERGE_GAP:
            last["end"] = start + WINDOW
            last["errors"] += count
            last["score"] = max(last["score"], count / threshold)
        else:
            spikes.append({"start": start, "end": start + WINDOW, "errors": count,
                           "score": count / threshold, "threshold": threshold,
                           "baseline": mean(counts)})
    return [
        (s["start"], s["end"], round(s["score"], 2), {
            "observed_errors": s["errors"],
            "baseline_average": round(s["baseline"], 2),
            "threshold": round(s["threshold"], 2),
            "window_minutes": int(WINDOW.total_seconds() // 60),
            "baseline_type": "previous_24_hours",
        })
        for s in spikes
    ]
