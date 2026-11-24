"""Map raw log levels to DEBUG | INFO | WARN | ERROR | FATAL."""

LEVELS = ("DEBUG", "INFO", "WARN", "ERROR", "FATAL")

_MAP = {
    "TRACE": "DEBUG", "DEBUG": "DEBUG", "DBG": "DEBUG", "VERBOSE": "DEBUG",
    "INFO": "INFO", "INFORMATION": "INFO", "NOTICE": "INFO", "I": "INFO",
    "WARN": "WARN", "WARNING": "WARN", "W": "WARN",
    "ERROR": "ERROR", "ERR": "ERROR", "E": "ERROR",
    "FATAL": "FATAL", "CRITICAL": "FATAL", "CRIT": "FATAL", "SEVERE": "FATAL",
    "EMERG": "FATAL", "EMERGENCY": "FATAL", "ALERT": "FATAL",
}


def normalize_level(raw: str | None) -> str | None:
    """Normalized level, or None if the raw value is unknown (level_raw keeps the original)."""
    if raw is None:
        return None
    return _MAP.get(raw.strip().upper())
