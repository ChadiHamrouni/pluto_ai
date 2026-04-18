"""Deterministic idempotency key generator for batch tool operations."""

from __future__ import annotations

import hashlib


def make_key(*parts: str) -> str:
    """Return a 16-char hex digest from the concatenated parts.

    Usage: make_key(title, start_time)  →  'a3f1c2d4e5b67890'
    Re-submitting the same logical item produces the same key, so the DB
    layer can skip the duplicate insert.
    """
    raw = "|".join(p.strip().lower() for p in parts)
    return hashlib.sha256(raw.encode()).hexdigest()[:16]
