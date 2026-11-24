"""Read log files: decompress .gz in memory, detect the encoding, split into lines.

The log package contains UTF-8 files and at least one Windows-1252 file, CRLF and LF line
endings, and gzip-compressed JSONL. Files on disk are never modified.
"""

import gzip
from pathlib import Path

UTF8_BOM = b"\xef\xbb\xbf"


def read_bytes(path: Path) -> bytes:
    """File content as bytes, decompressed if the file ends with .gz."""
    data = Path(path).read_bytes()
    return gzip.decompress(data) if Path(path).suffix == ".gz" else data


def decode(data: bytes) -> tuple[str, str]:
    """Return (text, encoding). Tries UTF-8 (with or without BOM), falls back to Windows-1252."""
    if data.startswith(UTF8_BOM):
        return data[len(UTF8_BOM):].decode("utf-8", errors="replace"), "utf-8-sig"
    try:
        return data.decode("utf-8"), "utf-8"
    except UnicodeDecodeError:
        # cp1252 leaves a few bytes undefined; replace them instead of failing.
        return data.decode("cp1252", errors="replace"), "cp1252"


def split_lines(text: str) -> list[str]:
    """Split on \\n only (not on other Unicode separators) and strip a trailing \\r.

    Line i of the file is lines[i - 1]. A final newline does not create an empty last line.
    """
    lines = text.split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    return [line.removesuffix("\r") for line in lines]


def read_text(path: Path) -> tuple[str, str]:
    """Convenience: read, decompress and decode a file. Returns (text, encoding)."""
    return decode(read_bytes(path))
