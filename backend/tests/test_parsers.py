"""Parser tests with real line shapes from the log package."""

import json

from logtracer.ingest.detector import detect_format
from logtracer.ingest.models import ParseContext
from logtracer.ingest.parse_run import infer_default_date
from logtracer.ingest.parsers import parse

CTX = ParseContext(host="mait_test", component="app/comp")

KV = (
    "2026-11-23T08:00:14Z WARN host=mait_linux1 component=os/network event_id=E-00003600 "
    "job_id=NORMAL-03444 | Transient latency; retry succeeded\r\n"
    "2026-11-23T08:00:37Z INFO host=mait_linux1 component=os/network event_id=E-00003601 "
    "job_id=NORMAL-07475 | Operation completed duration_ms=487 object=DEMO-00453\r\n"
)

BRACKET = (
    "2026-11-24T08:30:08Z [ERROR] host=mait_linux1_teamcenter_app component=fms/fsc "
    "event_id=CREATIVE-00045771 job_id=JOB-2003 | "
    '{"message": "Upload rejected; access policy lacks target volume write permission"}\n'
    "2026-11-24T08:08:34Z [ERROR] host=mait_win02_dispatcher_worker component=dispatcher/module "
    "event_id=CREATIVE-00045763 job_id=JOB-2001 | "
    '{"message": "Worker failed after request; local clock is behind; sequence=2", '
    '"clock_offset_seconds": -94, "trace_id": "TRACE-2001", "observed_at": "2026-11-24T08:10:08Z"}\n'
)

CSV = (
    "timestamp;level;host;component;event_id;job_id;message;duration_ms;session_id\r\n"
    "2026-11-24T08:30:00Z;INFO;mait_win03_cad_converter;converter/nx_jt;CREATIVE-00045769;JOB-2003;"
    '"Conversion succeeded; JT output=DEMO-301.jt checksum=abc123";;\r\n'
    "2026-11-24T11:01:00Z;ERROR;mait_win03_cad_converter;converter/nx_jt;CREATIVE-00045827;JOB-2010;"
    '"SyntheticConversionException: reference missing\r\n'
    "  at demo.converter.resolve(Resolver.java:82)\r\n"
    'Caused by: MissingReferenceException: DEMO-Seal-17/C";;\r\n'
    "2026-11-24T11:01:34Z;INFO;mait_win03_cad_converter;converter/nx_jt;CREATIVE-00012491;OK-05411;"
    '"Preflight succeeded; units=mm tolerance=0.01";263;DEMO-S-05\r\n'
)

JSONL = "\n".join([
    json.dumps({"timestamp": "2026-11-24T08:30:12Z", "level": "ERROR",
                "host": "mait_linux1_teamcenter_app", "component": "teamcenter/workflow",
                "event_id": "CREATIVE-00045772", "job_id": "JOB-2003",
                "message": "Publish task failed: no registered result; converter status=SUCCESS"}),
    json.dumps({"timestamp": "2026-10-05T09:03:19Z", "host": "mait_linux1_teamcenter_app",
                "level": "ERROR", "component": "teamcenter", "event_id": "EV-04-06-000342",
                "trace_id": "TRACE-05-000", "job_id": "PLM-05-000", "duration_ms": 500,
                "message": "Downstream timeout/retry during INC-01; "
                           "dependency=mait_linux2_teamcenter_db", "synthetic": True}),
    "{not json",
]) + "\n"

XML = (
    '<Events synthetic="true">\n'
    "<Event><timestamp>2026-11-24T08:00:57Z</timestamp><level>WARN</level>"
    "<host>mait_linux1_teamcenter_app</host><component>converter/converter_iges</component>"
    "<event_id>CREATIVE-00023101</event_id><job_id>OK-02436</job_id>"
    "<message>Temporary slowdown; retry completed successfully; no lost work</message>"
    "<duration_ms>210</duration_ms><session_id>DEMO-S-31</session_id></Event>\n"
    "</Events>\n"
)

FREETEXT = (
    "2026-10-06 14:02:15.234 [INFO] Dispatcher initialization started on mait_win01\n"
    "2026-10-06T14:02:47.123Z [ERROR] Job 4711 failed: converter timeout\n"
    "2026-10-06 14:03:01.234 | INFO | CONVERTER_JT | product_ABC_v2.3.prt | STARTED | Processing\n"
    "2026-10-06 14:02:16.000 [INFO] mait_win04_plm_sync - License service startup initiated\n"
    "[2026-10-06 14:03:01] TC.ERROR - Workflow step blocked - converter error detected\n"
    "[14:02:15] TC.RAC - User authentication successful\n"
    "    continuation of the previous entry\n"
)


def test_detect_format_by_extension_and_content():
    assert detect_format("x/a.jsonl.gz", "") == "jsonl"
    assert detect_format("x/a.csv", "") == "csv_semicolon"
    assert detect_format("x/a.xml", "") == "xml_events"
    assert detect_format("x/creative_2026-11-24.log", BRACKET) == "bracket_json"  # .log, but JSON
    assert detect_format("x/2026-11-23.log", KV) == "kv_log"
    assert detect_format("x/import_sample.log", FREETEXT) == "freetext"


def test_kv_log():
    events = parse("kv_log", KV, CTX)
    assert len(events) == 2
    first, second = events
    assert (first.ts, first.level_raw, first.host, first.component) == (
        "2026-11-23T08:00:14Z", "WARN", "mait_linux1", "os/network")
    assert (first.event_id, first.job_id) == ("E-00003600", "NORMAL-03444")
    assert first.message == "Transient latency; retry succeeded"
    assert second.attrs == {"duration_ms": 487, "object": "DEMO-00453"}
    assert first.raw.endswith("retry succeeded")  # \r stripped


def test_bracket_json_with_extra_fields():
    upload, clock = parse("bracket_json", BRACKET, CTX)
    assert upload.message.startswith("Upload rejected")
    assert upload.job_id == "JOB-2003" and upload.level_raw == "ERROR"
    assert clock.trace_id == "TRACE-2001"
    assert clock.attrs == {"clock_offset_seconds": -94, "observed_at": "2026-11-24T08:10:08Z"}


def test_csv_multiline_stack_trace_keeps_line_numbers():
    events = parse("csv_semicolon", CSV, CTX)
    assert [(e.line_start, e.line_end) for e in events] == [(2, 2), (3, 5), (6, 6)]
    exc = events[1]
    assert exc.message.startswith("SyntheticConversionException")
    assert "Caused by: MissingReferenceException: DEMO-Seal-17/C" in exc.message
    assert exc.raw.count("\n") == 2
    assert events[2].attrs == {"duration_ms": 263}
    assert events[2].session_id == "DEMO-S-05"
    assert all(e.parse_error is None for e in events)


def test_jsonl_with_trace_id_and_invalid_line():
    publish, incident, broken = parse("jsonl", JSONL, CTX)
    assert publish.ts == "2026-11-24T08:30:12Z" and publish.job_id == "JOB-2003"
    assert incident.trace_id == "TRACE-05-000"
    assert incident.attrs == {"duration_ms": 500, "synthetic": True}
    assert broken.parse_error.startswith("invalid JSON")
    assert broken.raw == "{not json"


def test_xml_events():
    (event,) = parse("xml_events", XML, CTX)
    assert event.line_start == 2
    assert event.level_raw == "WARN" and event.event_id == "CREATIVE-00023101"
    assert event.attrs == {"duration_ms": 210}
    assert event.session_id == "DEMO-S-31"


def test_freetext_variants():
    ctx = ParseContext(host="mait_win01_dispatcher_master", component="dispatcher/core",
                       default_date="2026-10-06")
    events = parse("freetext", FREETEXT, ctx)
    assert len(events) == 6
    plain, iso, pipe, mixed_host, tagged, time_only = events
    assert plain.ts == "2026-10-06T14:02:15.234" and plain.level_raw == "INFO"
    assert plain.host == "mait_win01_dispatcher_master"  # from the folder
    assert iso.ts == "2026-10-06T14:02:47.123Z" and iso.level_raw == "ERROR"
    assert pipe.attrs == {"module": "CONVERTER_JT", "object": "product_ABC_v2.3.prt",
                          "stage": "STARTED"}
    assert mixed_host.host == "mait_win04_plm_sync"  # host named in the line wins
    assert tagged.level_raw == "ERROR" and tagged.ts == "2026-10-06T14:03:01"
    assert time_only.ts == "2026-10-06T14:02:15" and time_only.attrs["time_only"] is True
    assert time_only.line_end == 7  # continuation line attached
    assert all(e.parse_error is None for e in events)


def test_freetext_time_only_without_default_date_is_flagged():
    (event,) = parse("freetext", "[14:02:15] TC.RAC - User authentication successful\n", CTX)
    assert event.ts is None and event.parse_error is not None


def test_infer_default_date():
    assert infer_default_date(["[2026-10-06 14:02:15] a", "2026-10-06 14:03 b",
                               "2026-11-24T08:00 c"]) == "2026-10-06"
    assert infer_default_date(["[14:02:15] only times"]) is None
