"""Shared parser output. Every parser returns a list of RawEvent, whatever the input format."""

from dataclasses import dataclass, field

# Fields that have their own column in `events`; everything else from a log line goes to attrs.
KNOWN_FIELDS = ("host", "component", "event_id", "job_id", "trace_id", "session_id")


@dataclass(frozen=True)
class ParseContext:
    """What a parser knows about the file besides its content."""

    host: str  # server folder; used when the line has no host
    component: str | None  # "<application>/<component>" from the path; used when the line has none
    default_date: str | None = None  # YYYY-MM-DD for lines that only carry a time of day


@dataclass(slots=True)
class RawEvent:
    line_start: int  # 1-based line in the decompressed file
    line_end: int
    raw: str  # original text of all lines of the entry
    ts_raw: str | None = None  # timestamp text exactly as found
    ts: str | None = None  # ISO 8601; ends with Z when the source is UTC, no suffix = no time zone
    level_raw: str | None = None
    host: str | None = None
    component: str | None = None
    event_id: str | None = None
    job_id: str | None = None
    trace_id: str | None = None
    session_id: str | None = None
    message: str | None = None
    attrs: dict = field(default_factory=dict)
    parse_error: str | None = None

    def append_line(self, line: str, line_no: int) -> None:
        """Attach a continuation line (e.g. a stack trace line) to this entry."""
        self.raw = f"{self.raw}\n{line}"
        self.message = f"{self.message}\n{line}" if self.message else line
        self.line_end = line_no

    def set_fields(self, fields: dict) -> None:
        """Put known keys into their attributes and the rest into attrs."""
        for key, value in fields.items():
            if value is None or value == "":
                continue
            if key in KNOWN_FIELDS:
                setattr(self, key, str(value))
            else:
                self.attrs[key] = coerce(value)


def coerce(value):
    """Turn numeric strings into numbers, keep everything else."""
    if isinstance(value, str):
        if value.lstrip("-").isdigit():
            try:
                return int(value)
            except ValueError:
                return value
        if value.lower() in ("true", "false"):
            return value.lower() == "true"
    return value
