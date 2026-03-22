"""Shared time utilities for governance runtime."""

from __future__ import annotations

from datetime import datetime, timezone


def now_iso() -> str:
    """Return current UTC time as ISO 8601 with no microseconds."""
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
