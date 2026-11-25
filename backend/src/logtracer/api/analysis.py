"""Read-only API endpoints for P2 log analysis."""

from typing import Annotated

import duckdb
from fastapi import APIRouter, Depends, HTTPException, Query

from logtracer.analysis.graph import build_graph
from logtracer.api.deps import get_cursor

Cursor = Annotated[duckdb.DuckDBPyConnection, Depends(get_cursor)]

router = APIRouter(prefix="/api/analysis", tags=["Analysis"])


@router.get("/stats")
def analysis_stats(
    con: Cursor,
):
    tables = [
        "events",
        "error_groups",
        "anomalies",
        "correlations",
        "incidents",
    ]

    counts = {}

    for table in tables:
        counts[table] = con.execute(
            f"SELECT COUNT(*) FROM {table}"
        ).fetchone()[0]

    return {"counts": counts}


@router.get("/incidents")
def list_incidents(
    con: Cursor,
    limit: int = Query(default=50, ge=1, le=500),
):
    rows = con.execute("""
        SELECT
            incident_id, title, first_ts, last_ts,
            status, hosts, group_ids,
            root_group_id, confidence
        FROM incidents
        ORDER BY first_ts DESC NULLS LAST, incident_id
        LIMIT ?
    """, [limit]).fetchall()

    return [
        {
            "incident_id": row[0],
            "title": row[1],
            "first_ts": row[2],
            "last_ts": row[3],
            "status": row[4],
            "hosts": row[5],
            "group_ids": row[6],
            "root_group_id": row[7],
            "confidence": row[8],
        }
        for row in rows
    ]


@router.get("/incidents/{incident_id}")
def incident_detail(
    incident_id: int,
    con: Cursor,
):
    row = con.execute("""
        SELECT
            incident_id, title, first_ts, last_ts,
            status, hosts, group_ids,
            root_group_id, confidence
        FROM incidents
        WHERE incident_id = ?
    """, [incident_id]).fetchone()

    if row is None:
        raise HTTPException(
            status_code=404,
            detail="Incident not found",
        )

    return {
        "incident_id": row[0],
        "title": row[1],
        "first_ts": row[2],
        "last_ts": row[3],
        "status": row[4],
        "hosts": row[5],
        "group_ids": row[6],
        "root_group_id": row[7],
        "confidence": row[8],
    }


@router.get("/anomalies")
def list_anomalies(
    con: Cursor,
    limit: int = Query(default=50, ge=1, le=500),
):
    rows = con.execute("""
        SELECT
            anomaly_id, host, component, kind,
            window_start, window_end, score, details
        FROM anomalies
        ORDER BY window_start DESC NULLS LAST
        LIMIT ?
    """, [limit]).fetchall()

    return [
        {
            "anomaly_id": row[0],
            "host": row[1],
            "component": row[2],
            "kind": row[3],
            "window_start": row[4],
            "window_end": row[5],
            "score": row[6],
            "details": row[7],
        }
        for row in rows
    ]


@router.get("/graph")
def analysis_graph(
    con: Cursor,
):
    return build_graph(con)
