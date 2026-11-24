"""One parser per log format, all returning list[RawEvent] (P1)."""

from collections.abc import Callable

from logtracer.ingest.models import ParseContext, RawEvent
from logtracer.ingest.parsers.line_based import parse_bracket_json, parse_freetext, parse_kv_log
from logtracer.ingest.parsers.structured import (
    parse_csv_semicolon,
    parse_jsonl,
    parse_xml_events,
)

Parser = Callable[[str, ParseContext], list[RawEvent]]

PARSERS: dict[str, Parser] = {
    "kv_log": parse_kv_log,
    "bracket_json": parse_bracket_json,
    "csv_semicolon": parse_csv_semicolon,
    "jsonl": parse_jsonl,
    "xml_events": parse_xml_events,
    "freetext": parse_freetext,
}


def parse(fmt: str, text: str, ctx: ParseContext) -> list[RawEvent]:
    return PARSERS[fmt](text, ctx)
