"""Structured formats: csv_semicolon, jsonl and xml_events."""

import csv
import io
import json
import re
import xml.etree.ElementTree as ET

from logtracer.ingest.models import ParseContext, RawEvent
from logtracer.ingest.reader import split_lines

# --- csv_semicolon ------------------------------------------------------------------------
# Header: timestamp;level;host;component;event_id;job_id;message[;duration_ms;session_id]
# Messages can contain quoted multi-line Java stack traces, so the csv module does the
# splitting; line_start/line_end come from the reader's physical line counter.


def parse_csv_semicolon(text: str, ctx: ParseContext) -> list[RawEvent]:
    lines = split_lines(text)
    reader = csv.reader(io.StringIO(text, newline=""), delimiter=";")
    events: list[RawEvent] = []
    header: list[str] | None = None
    previous_end = 0
    for row in reader:
        start, end = previous_end + 1, reader.line_num
        previous_end = end
        if not row or not any(cell.strip() for cell in row):
            continue
        if header is None:
            header = [h.strip() for h in row]
            continue
        raw = "\n".join(lines[start - 1:end])
        if len(row) < len(header):
            row = row + [""] * (len(header) - len(row))
        record = dict(zip(header, row, strict=False))
        extra = row[len(header):]
        event = RawEvent(start, end, raw, ts_raw=record.pop("timestamp", None) or None,
                         level_raw=record.pop("level", None) or None,
                         message=record.pop("message", None))
        event.ts = event.ts_raw
        event.set_fields(record)
        if any(cell.strip() for cell in extra):
            event.attrs["extra_columns"] = [c for c in extra if c.strip()]
        if event.ts_raw is None:
            event.parse_error = "row without timestamp"
        event.host = event.host or ctx.host
        event.component = event.component or ctx.component
        events.append(event)
    return events


# --- jsonl ----------------------------------------------------------------------------------


def parse_jsonl(text: str, ctx: ParseContext) -> list[RawEvent]:
    events: list[RawEvent] = []
    for line_no, line in enumerate(split_lines(text), start=1):
        if not line.strip():
            continue
        event = RawEvent(line_no, line_no, line, host=ctx.host, component=ctx.component)
        try:
            data = json.loads(line)
        except json.JSONDecodeError as exc:
            event.message = line
            event.parse_error = f"invalid JSON: {exc.msg}"
            events.append(event)
            continue
        if not isinstance(data, dict):
            event.message = line
            event.parse_error = "JSON line is not an object"
            events.append(event)
            continue
        event.ts_raw = event.ts = data.pop("timestamp", None)
        event.level_raw = data.pop("level", None)
        event.message = data.pop("message", None)
        event.set_fields(data)
        events.append(event)
    return events


# --- xml_events -----------------------------------------------------------------------------
# <Events synthetic="true">
# <Event><timestamp>…</timestamp><level>…</level>…<message>…</message></Event>
# </Events>
# Every <Event> is on its own line, so line numbers come for free.

_EVENT_LINE = re.compile(r"^\s*<Event>.*</Event>\s*$")
_WRAPPER_LINE = re.compile(r"^\s*(<\?xml[^>]*\?>\s*)?(<Events\b[^>]*>|</Events>)\s*$")


def parse_xml_events(text: str, ctx: ParseContext) -> list[RawEvent]:
    events: list[RawEvent] = []
    for line_no, line in enumerate(split_lines(text), start=1):
        if not line.strip() or _WRAPPER_LINE.match(line):
            continue
        event = RawEvent(line_no, line_no, line, host=ctx.host, component=ctx.component)
        if not _EVENT_LINE.match(line):
            if events and events[-1].parse_error is None and not line.lstrip().startswith("<"):
                events[-1].append_line(line, line_no)
                continue
            event.message = line
            event.parse_error = "line is not a single <Event> element"
            events.append(event)
            continue
        try:
            element = ET.fromstring(line.strip())
        except ET.ParseError as exc:
            event.message = line
            event.parse_error = f"invalid XML: {exc}"
            events.append(event)
            continue
        data = {child.tag: (child.text or "") for child in element}
        event.ts_raw = event.ts = data.pop("timestamp", None) or None
        event.level_raw = data.pop("level", None) or None
        event.message = data.pop("message", None)
        event.set_fields(data)
        events.append(event)
    return events
