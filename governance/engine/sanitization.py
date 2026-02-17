"""Deterministic output sanitization helpers."""

from __future__ import annotations

import re
from typing import Any

_CREDENTIAL_URL = re.compile(r"(https?://)([^/@:\s]+):([^@/\s]+)@", flags=re.IGNORECASE)
_SECRET_KEY = re.compile(r"(secret|token|password|api[_-]?key|authorization)", flags=re.IGNORECASE)


def _sanitize_string(value: str) -> str:
    redacted = _CREDENTIAL_URL.sub(r"\1\2:***@", value)
    return redacted


def sanitize_for_output(payload: Any) -> Any:
    """Recursively sanitize values for user-visible output payloads."""

    if isinstance(payload, str):
        return _sanitize_string(payload)
    if isinstance(payload, list):
        return [sanitize_for_output(item) for item in payload]
    if isinstance(payload, tuple):
        return tuple(sanitize_for_output(item) for item in payload)
    if isinstance(payload, dict):
        out: dict[str, Any] = {}
        for key, value in payload.items():
            key_s = str(key)
            if _SECRET_KEY.search(key_s):
                out[key_s] = "***"
            else:
                out[key_s] = sanitize_for_output(value)
        return out
    return payload
