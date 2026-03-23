"""Deterministic output sanitization helpers."""

from __future__ import annotations

import re
from typing import Any

_CREDENTIAL_URL = re.compile(r"(https?://)([^/@:\s]+):([^@/\s]+)@", flags=re.IGNORECASE)
_SECRET_KEY = re.compile(
    r"(secret|token|password|api[_-]?key|authorization"
    r"|private[_-]?key|access[_-]?token|bearer|jwt[_-]?secret"
    r"|client[_-]?secret|refresh[_-]?token|signing[_-]?key)",
    flags=re.IGNORECASE,
)
_FILESYSTEM_PATH = re.compile(
    r"(?:(?:/(?:Users|home|root|tmp|var|etc)/[^\s\"']+)"
    r"|(?:[A-Z]:\\[^\s\"']+))",
)


def _sanitize_string(value: str) -> str:
    redacted = _CREDENTIAL_URL.sub(r"\1\2:***@", value)
    redacted = _FILESYSTEM_PATH.sub("[path-redacted]", redacted)
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


_BUSINESS_RULES_REFERENCE_KEYS = {
    "Rules",
    "Evidence",
    "EvidenceRefs",
    "EvidencePaths",
    "ReferencePaths",
    "References",
    "SourceFiles",
}


def apply_fresh_start_business_rules_neutralization(state: dict[str, Any]) -> None:
    """Normalize BusinessRules to a fail-closed fresh-start state.

    This helper intentionally handles only BusinessRules-related normalization.
    Callers manage transition-level fields (for example phase_transition_evidence)
    in their own context.
    """

    scope_obj = state.get("Scope")
    scope = dict(scope_obj) if isinstance(scope_obj, dict) else {}
    scope["BusinessRules"] = "unresolved"
    state["Scope"] = scope

    business_obj = state.get("BusinessRules")
    business_rules = dict(business_obj) if isinstance(business_obj, dict) else {}

    for key in _BUSINESS_RULES_REFERENCE_KEYS:
        business_rules.pop(key, None)

    business_rules.pop("InventoryFilePath", None)
    business_rules["Decision"] = "pending"
    business_rules["Outcome"] = "unresolved"
    business_rules["ExecutionEvidence"] = False
    business_rules["InventoryLoaded"] = False
    business_rules["InventoryFileStatus"] = "unknown"
    business_rules["InventoryFileMode"] = "unknown"
    business_rules["ExtractedCount"] = 0
    business_rules["Inventory"] = {
        "sha256": "0" * 64,
        "count": 0,
    }

    state["BusinessRules"] = business_rules
