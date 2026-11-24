"""Line-based formats: kv_log, bracket_json and freetext.

A line that does not start a new entry is a continuation of the previous entry (stack traces).
A continuation before the first entry becomes its own event with parse_error set.
"""

import json
import re
from collections.abc import Callable

from logtracer.ingest.models import ParseContext, RawEvent, coerce
from logtracer.ingest.reader import split_lines

LineMatcher = Callable[[str, int, ParseContext], RawEvent | None]

_FIELDS = r"(?P<fields>(?:[\w.]+=\S+ )*)"
_KV_PAIR = re.compile(r"([\w.]+)=(\S+)")

# 2026-11-23T08:00:14Z WARN host=… component=… event_id=… job_id=… | Transient latency; retry succeeded
KV_LINE = re.compile(rf"^(?P<ts>\S+) (?P<level>[A-Za-z]+) {_FIELDS}\| ?(?P<msg>.*)$")

# 2026-11-24T08:30:08Z [ERROR] host=… component=… event_id=… job_id=… | {"message": "…"}
BRACKET_LINE = re.compile(rf"^(?P<ts>\S+) \[(?P<level>[A-Za-z]+)\] {_FIELDS}\| ?(?P<payload>.*)$")


def _parse_lines(text: str, ctx: ParseContext, match_line: LineMatcher) -> list[RawEvent]:
    events: list[RawEvent] = []
    for line_no, line in enumerate(split_lines(text), start=1):
        if not line.strip():
            continue
        event = match_line(line, line_no, ctx)
        if event is not None:
            event.host = event.host or ctx.host
            event.component = event.component or ctx.component
            events.append(event)
        elif events:
            events[-1].append_line(line, line_no)
        else:
            events.append(RawEvent(line_no, line_no, line, message=line, host=ctx.host,
                                   component=ctx.component,
                                   parse_error="continuation line before the first entry"))
    return events


def _kv_fields(text: str) -> dict:
    return dict(_KV_PAIR.findall(text))


# --- kv_log -------------------------------------------------------------------------------

def _match_kv(line: str, line_no: int, ctx: ParseContext) -> RawEvent | None:
    m = KV_LINE.match(line)
    if not m:
        return None
    event = RawEvent(line_no, line_no, line, ts_raw=m["ts"], ts=m["ts"], level_raw=m["level"],
                     message=m["msg"])
    event.set_fields(_kv_fields(m["fields"]))
    # key=value pairs inside the message (duration_ms=487 object=DEMO-00453) go to attrs too
    for key, value in _kv_fields(m["msg"]).items():
        event.attrs.setdefault(key, coerce(value))
    return event


def parse_kv_log(text: str, ctx: ParseContext) -> list[RawEvent]:
    return _parse_lines(text, ctx, _match_kv)


# --- bracket_json -------------------------------------------------------------------------

def _match_bracket(line: str, line_no: int, ctx: ParseContext) -> RawEvent | None:
    m = BRACKET_LINE.match(line)
    if not m:
        return None
    event = RawEvent(line_no, line_no, line, ts_raw=m["ts"], ts=m["ts"], level_raw=m["level"])
    event.set_fields(_kv_fields(m["fields"]))
    payload = m["payload"]
    try:
        data = json.loads(payload) if payload.startswith("{") else None
    except json.JSONDecodeError:
        data = None
    if isinstance(data, dict):
        event.message = data.pop("message", None)
        event.set_fields(data)
    else:
        event.message = payload
    return event


def parse_bracket_json(text: str, ctx: ParseContext) -> list[RawEvent]:
    return _parse_lines(text, ctx, _match_bracket)


# --- freetext (import_*.log) --------------------------------------------------------------

_TS = r"\d{4}-\d\d-\d\d[ T]\d\d:\d\d:\d\d(?:\.\d+)?Z?"

# 2026-10-06 14:03:01.234 | INFO | CONVERTER_JT | product_ABC_v2.3.prt | STARTED | Processing …
FT_PIPE = re.compile(rf"^(?P<ts>{_TS}) \| (?P<level>[A-Za-z]+) \| (?P<rest>.*)$")
# 2026-10-06 14:02:15.234 [INFO] message            (optionally: "<host> - message")
# 2026-10-06T14:02:15.234Z [INFO] message
FT_BRACKET = re.compile(
    rf"^(?P<ts>{_TS}) \[(?P<level>[A-Za-z]+)\] (?:(?P<host>mait_\w+) - )?(?P<msg>.*)$"
)
# [2026-10-06 14:02:15] TC.RAC - message   or   [14:02:15] TC.RAC - message (time only)
FT_TAGGED = re.compile(
    r"^\[(?P<ts>(?:\d{4}-\d\d-\d\d )?\d\d:\d\d:\d\d(?:\.\d+)?)\] (?P<tag>[\w.]+) - (?P<msg>.*)$"
)


def _iso(ts: str) -> str:
    return ts.replace(" ", "T", 1)


def _tag_level(tag: str) -> str:
    upper = tag.upper()
    for level in ("FATAL", "CRITICAL", "ERROR", "WARNING", "WARN", "DEBUG"):
        if upper.endswith(level):
            return level
    return "INFO"


def _match_freetext(line: str, line_no: int, ctx: ParseContext) -> RawEvent | None:
    if m := FT_PIPE.match(line):
        parts = [p.strip() for p in m["rest"].split(" | ")]
        event = RawEvent(line_no, line_no, line, ts_raw=m["ts"], ts=_iso(m["ts"]),
                         level_raw=m["level"], message=parts[-1])
        for key, value in zip(("module", "object", "stage"), parts[:-1], strict=False):
            event.attrs[key] = value
        return event
    if m := FT_BRACKET.match(line):
        return RawEvent(line_no, line_no, line, ts_raw=m["ts"], ts=_iso(m["ts"]),
                        level_raw=m["level"], host=m["host"], message=m["msg"])
    if m := FT_TAGGED.match(line):
        ts_raw = m["ts"]
        event = RawEvent(line_no, line_no, line, ts_raw=ts_raw, level_raw=_tag_level(m["tag"]),
                         message=m["msg"])
        event.attrs["module"] = m["tag"]
        if len(ts_raw) > 12:  # has a date
            event.ts = _iso(ts_raw)
        elif ctx.default_date:
            event.ts = f"{ctx.default_date}T{ts_raw}"
            event.attrs["time_only"] = True
        else:
            event.attrs["time_only"] = True
            event.parse_error = "time of day only and no default date known"
        return event
    return None


def parse_freetext(text: str, ctx: ParseContext) -> list[RawEvent]:
    return _parse_lines(text, ctx, _match_freetext)
