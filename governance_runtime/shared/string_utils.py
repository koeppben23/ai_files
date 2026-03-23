"""Pure string utilities - stateless, no IO, no system dependencies.

This module belongs to the shared/support layer and can be imported
by any layer including application services.
"""

from __future__ import annotations


def safe_str(value: object) -> str:
    """Coerce a value to a stable scalar string for machine-readable output.

    This is a pure helper with no side effects.
    """
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def truncate_text(value: object, *, limit: int = 180) -> str:
    """Truncate a value to at most ``limit`` characters, appending '...' if truncated.

    Normalizes whitespace and returns 'none' for empty values.
    Pure helper with no side effects.
    """
    text = str(value or "").strip().replace("\n", " ")
    text = " ".join(text.split())
    if not text:
        return "none"
    if len(text) <= limit:
        return text
    return text[: limit - 3].rstrip() + "..."