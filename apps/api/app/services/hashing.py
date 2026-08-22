"""Content hashing.

A hash identifies an exact document. Approval binds to it, signature binds to
it, and any edit invalidates both (PRD LOP-M07-US-03).
"""

import hashlib
import json
from typing import Any


def canonical_json(value: Any) -> str:
    """A stable serialisation, so the same facts always hash the same way."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)


def content_hash(*parts: Any) -> str:
    """Hash the assembled content of a document."""
    digest = hashlib.sha256()
    for part in parts:
        digest.update(canonical_json(part).encode("utf-8"))
        digest.update(b"\x1e")
    return digest.hexdigest()


def file_hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()
