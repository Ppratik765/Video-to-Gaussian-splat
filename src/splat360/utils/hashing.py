"""
Stable fingerprints of files, config dicts, and code versions.

Used by the caching system in stages/base.py to decide whether a stage
needs to re-run.  All hashes are SHA-256 hex digests.

Responsibility: utils/hashing.py
Milestone: M0
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


def hash_file(path: Path, chunk_size: int = 1 << 16) -> str:
    """Return the SHA-256 hex digest of a file's contents."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def hash_dict(d: dict[str, Any]) -> str:
    """Return a deterministic SHA-256 hex digest of a JSON-serialisable dict.

    Keys are sorted recursively so the hash is independent of insertion order.
    """
    canonical = json.dumps(d, sort_keys=True, default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def hash_string(s: str) -> str:
    """Return the SHA-256 hex digest of a string."""
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def hash_bytes(b: bytes) -> str:
    """Return the SHA-256 hex digest of raw bytes."""
    return hashlib.sha256(b).hexdigest()
