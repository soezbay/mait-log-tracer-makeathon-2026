"""A tiny demo database: the JOB-2003 scenario from the plan plus noise (harmless ERROR, same job number twice)."""
from __future__ import annotations

from datetime import datetime

import duckdb

from logtracer.storage.db import init_schema

CONV = "mait_win03_cad_converter"
TC = "mait_linux1_teamcenter_app"
F_CSV = f"{CONV}/logs/converter/nx_jt/creative_2026-11-24.csv"
F_TXT = f"{TC}/logs/fms/fsc/creative_2026-11-24.txt"
F_JSONL = f"{TC}/logs/teamcenter/workflow/creative_2026-11-24.jsonl"


def build(con: duckdb.DuckDBPyConnection | None = None) -> duckdb.DuckDBPyConnection:
    con = con or duckdb.connect(":memory:")
    init_schema(con)  # the real storage/schema.sql (P1)
    d = lambda s: datetime.fromisoformat(s)
    con.executemany(
        "INSERT INTO sources (source_id, path, server, format) VALUES (?, ?, ?, ?)",
        [(1, F_CSV, CONV, "csv"), (2, F_TXT, TC, "txt"), (3, F_JSONL, TC, "jsonl"), (4, f"{TC}/logs/x/y/a.log", TC, "log")],
    )
    ev = [
        # id, src, line, ts, host, component, level, code, job, message
        (1001, 1, 31, "2026-11-24T08:30:00", CONV, "converter/nx_jt", "INFO", "CV-1", "JOB-2003", "Conversion succeeded; JT output=DEMO-301.jt"),
        (1002, 2, 29, "2026-11-24T08:30:08", TC, "fms/fsc", "ERROR", "FMS-7", "JOB-2003", "Upload rejected; access policy lacks target volume write permission"),
        (1003, 3, 30, "2026-11-24T08:30:12", TC, "teamcenter/workflow", "ERROR", "WF-9", "JOB-2003", "Publish task failed: no registered result; converter status=SUCCESS"),
        (1004, 4, 10, "2026-11-24T08:29:50", TC, "teamcenter/soa", "ERROR", "SOA-1", None, "Transient retry recovered"),
        (1010, 4, 20, "2026-11-24T10:00:00", TC, "teamcenter/soa", "ERROR", "SOA-2", "JOB-2010", "Reference target absent from exported input package"),
        (1011, 4, 21, "2026-11-24T11:01:00", TC, "teamcenter/soa", "ERROR", "SOA-3", "JOB-2010", "java.lang.NullPointerException in export"),
    ]
    con.executemany(
        "INSERT INTO events (id, source_id, line_start, line_end, ts_utc, ingest_seq, host, component, "
        "level, event_id, job_id, message, raw) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [
            (i, s, ln, ln, d(ts), i, h, c, lv, code, job, msg, f"{ts} {lv} job={job} {msg}")
            for i, s, ln, ts, h, c, lv, code, job, msg in ev
        ],
    )
    con.executemany(
        "INSERT INTO templates (template_id, template, count) VALUES (?, ?, ?)",
        [(1, "Transient retry recovered", 1),
         (2, "Upload rejected; access policy lacks write permission", 2)],
    )
    con.execute(
        "INSERT INTO error_groups (group_id, template_id, host, component, level, count, first_ts, "
        "last_ts, status) VALUES (1, 1, ?, 'teamcenter/soa', 'ERROR', 1, ?, ?, 'recovered')",
        [TC, d("2026-11-24T08:29:50"), d("2026-11-24T08:29:50")],
    )
    con.execute(
        "INSERT INTO error_groups (group_id, template_id, host, component, level, count, first_ts, "
        "last_ts, status) VALUES (2, 2, ?, 'fms/fsc', 'ERROR', 2, ?, ?, 'failed')",
        [TC, d("2026-11-24T08:30:08"), d("2026-11-24T08:30:12")],
    )
    con.executemany("INSERT INTO group_members (group_id, event_pk) VALUES (?, ?)",
                    [(1, 1004), (2, 1002), (2, 1003)])
    con.execute(
        "INSERT INTO correlations (correlation_id, group_a, group_b, kind, link_key, lag_s, "
        "confidence) VALUES (1, 1, 2, 'soft', 'close in time', 18, 0.3)"
    )
    con.execute(
        "INSERT INTO anomalies (anomaly_id, host, component, kind, window_start, window_end, score, "
        "details) VALUES (1, ?, 'fms/fsc', 'rate_spike', ?, ?, 3.2, ?)",
        [TC, d("2026-11-24T08:30:00"), d("2026-11-24T08:31:00"),
         '{"note": "Error rate spike on fms/fsc"}'],
    )
    con.execute(
        "INSERT INTO incidents (incident_id, title, first_ts, last_ts, status, hosts, group_ids, "
        "root_group_id, confidence) VALUES (1, 'Publish JOB-2003 fails', ?, ?, 'failed', ?, [2], 2, 0.8)",
        [d("2026-11-24T08:30:00"), d("2026-11-24T08:30:12"), [CONV, TC]],
    )
    return con
