"""File fingerprints for file-level deduplication.

The hash is computed over the decompressed bytes, so a .gz file and an identical plain file
get the same fingerprint. Most `_runNN` files in the log package are byte-identical copies.
"""

import hashlib


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class DuplicateIndex:
    """Remembers the first source_id per hash; later files with the same hash are duplicates."""

    def __init__(self) -> None:
        self._first: dict[str, int] = {}

    def add(self, digest: str, source_id: int) -> int | None:
        """Register a file. Returns the source_id of the original if this is a duplicate."""
        original = self._first.get(digest)
        if original is None:
            self._first[digest] = source_id
        return original

    def __len__(self) -> int:
        return len(self._first)
