"""Shared text utilities for governance runtime."""

from __future__ import annotations

import hashlib


def safe_str(value: object) -> str:
    """Coerce a value to a stable scalar string for machine-readable output."""
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def sha256_text(value: str) -> str:
    """Return hex SHA-256 digest of a UTF-8 encoded string."""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def truncate_text(value: object, *, limit: int = 180) -> str:
    """Truncate a value to at most ``limit`` characters, appending '...' if truncated.

    Normalizes whitespace and returns 'none' for empty values.
    """
    text = str(value or "").strip().replace("\n", " ")
    text = " ".join(text.split())
    if not text:
        return "none"
    if len(text) <= limit:
        return text
    return text[: limit - 3].rstrip() + "..."


def format_list(items: list) -> str:
    """Format a list into a bracketed, comma-separated string."""
    return "[" + ", ".join(safe_str(i) for i in items) + "]"
