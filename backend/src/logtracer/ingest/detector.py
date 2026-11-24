"""Detect the log format of a file from its name and first line.

The extension is not enough: in the log package `creative_*.log` files use the same
`TS [LEVEL] host=… | {json}` shape as the `.txt` files, while `2026-11-23*.log` files use
plain key=value. So `.log` and `.txt` are decided by content.
"""

import re

FORMATS = ("kv_log", "bracket_json", "csv_semicolon", "jsonl", "xml_events", "freetext")

BRACKET_JSON_START = re.compile(r"^\S+ \[[A-Za-z]+\] host=\S+ ")
KV_LOG_START = re.compile(r"^\S+ [A-Za-z]+ host=\S+ ")


def detect_format(path: str, text: str) -> str:
    name = path.lower()
    if name.endswith((".jsonl", ".jsonl.gz")):
        return "jsonl"
    if name.endswith(".csv"):
        return "csv_semicolon"
    if name.endswith(".xml"):
        return "xml_events"

    first = next((line for line in text.splitlines() if line.strip()), "")
    if BRACKET_JSON_START.match(first):
        return "bracket_json"
    if KV_LOG_START.match(first):
        return "kv_log"
    return "freetext"
