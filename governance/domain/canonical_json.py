from __future__ import annotations

import hashlib
import json
from typing import Any


def _normalize_string_newlines(value: str) -> str:
    return value.replace("\r\n", "\n").replace("\r", "\n")


def _normalize_payload_strings(payload: Any) -> Any:
    if isinstance(payload, str):
        return _normalize_string_newlines(payload)
    if isinstance(payload, list):
        return [_normalize_payload_strings(item) for item in payload]
    if isinstance(payload, tuple):
        return [_normalize_payload_strings(item) for item in payload]
    if isinstance(payload, dict):
        return {str(key): _normalize_payload_strings(value) for key, value in payload.items()}
    return payload


def canonical_json_text(payload: Any) -> str:
    normalized = _normalize_payload_strings(payload)
    return json.dumps(normalized, sort_keys=True, ensure_ascii=True, separators=(",", ":"))


def canonical_json_hash(payload: Any) -> str:
    return hashlib.sha256(canonical_json_text(payload).encode("utf-8")).hexdigest()
