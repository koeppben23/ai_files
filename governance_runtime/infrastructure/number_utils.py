"""Shared number utilities for governance runtime."""

from __future__ import annotations


def coerce_int(value: object) -> int:
    """Coerce a value to a non-negative int, defaulting to 0."""
    if value is None:
        return 0
    try:
        if isinstance(value, bool):
            return 1 if value else 0
        result = int(value)  # type: ignore[arg-type]
        return max(0, result)
    except (TypeError, ValueError):
        return 0


def quote_if_needed(value: str) -> str:
    """Wrap value in double quotes when it includes key-value delimiters."""
    if any(c in value for c in (":", "#", "'", '"', "{", "}", "[", "]", ",", "&", "*", "?", "|", "-", "<", ">", "=", "!", "%", "@", "`")):
        escaped = value.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'
    return value
