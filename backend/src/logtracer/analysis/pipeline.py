"""Run the whole analysis (P2) on the ingested events.

Started by the ingest manager after each ingest and by scripts/ingest.py. It rebuilds all
analysis tables in one transaction, so readers see either the old or the new result.
Only one process may write the DuckDB file, like for the ingest.
"""

import logging
import time
from dataclasses import dataclass, field

import duckdb

from logtracer.analysis.anomalies import build_anomalies
from logtracer.analysis.correlation import build_correlations
from logtracer.analysis.error_groups import build_error_groups
from logtracer.analysis.incidents import build_incidents
from logtracer.analysis.jobs import build_jobs
from logtracer.analysis.problems import atomic
from logtracer.analysis.templates import build_templates
from logtracer.normalize.clock import apply_declared_offsets

log = logging.getLogger("logtracer.analysis")

STEPS = (
    ("clock", apply_declared_offsets),
    ("templates", build_templates),
    ("error_groups", build_error_groups),
    ("correlations", build_correlations),
    ("incidents", build_incidents),
    ("anomalies", build_anomalies),
    ("jobs", build_jobs),
)


@dataclass
class AnalysisResult:
    elapsed_s: float
    steps: dict[str, float] = field(default_factory=dict)  # seconds per step
    counts: dict[str, int] = field(default_factory=dict)


def run_analysis(con: duckdb.DuckDBPyConnection) -> AnalysisResult:
    started = time.perf_counter()
    steps, counts = {}, {}
    with atomic(con):
        for name, step in STEPS:
            step_started = time.perf_counter()
            counts.update(step(con))
            steps[name] = round(time.perf_counter() - step_started, 2)
    result = AnalysisResult(round(time.perf_counter() - started, 2), steps, counts)
    log.info("analysis: %s incidents, %s error groups, %s anomalies in %.1f s",
             counts["incidents_created"], counts["groups_created"],
             counts["anomalies_detected"], result.elapsed_s)
    return result


def is_needed(con: duckdb.DuckDBPyConnection) -> bool:
    """True if there are events but no results for them, e.g. after a new table was added."""
    return con.execute(
        """
        SELECT EXISTS (SELECT 1 FROM events) AND (
            NOT EXISTS (SELECT 1 FROM templates)
            OR (NOT EXISTS (SELECT 1 FROM jobs)
                AND EXISTS (SELECT 1 FROM events WHERE trim(coalesce(job_id, '')) <> ''
                            AND ts_utc IS NOT NULL)))
        """
    ).fetchone()[0]
