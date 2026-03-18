"""Redaction Engine — Infrastructure adapter for field-level redaction on export.

Applies redaction rules from the classification domain model to produce
export-safe copies of audit artifacts. All operations are pure functions
that return new dicts (no mutation of inputs, no I/O).

Design:
    - Pure functions operating on dicts
    - Uses classification.py as SSOT for redaction rules
    - Deterministic: same input + same policy = same output
    - Fail-closed: unknown fields are redacted with HASH strategy
    - Zero external dependencies (stdlib only + governance.domain)
"""

from __future__ import annotations

import hashlib
import re
from typing import Any, Mapping, Optional

from governance_runtime.domain.classification import (
    ClassificationLevel,
    FieldClassification,
    RedactionStrategy,
    classify_field,
    DEFAULT_CLASSIFICATION,
)


# ---------------------------------------------------------------------------
# Redaction primitives
# ---------------------------------------------------------------------------

def _hash_value(value: str) -> str:
    """Replace a string value with its SHA-256 hash prefix."""
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()
    return f"[REDACTED:sha256:{digest[:16]}]"


def _mask_value(value: str, visible_chars: int = 4) -> str:
    """Mask a string value, preserving only the last N characters."""
    if len(value) <= visible_chars:
        return "[REDACTED]"
    return "[REDACTED:..." + value[-visible_chars:] + "]"


def _truncate_value(value: str, max_length: int = 32) -> str:
    """Truncate a string value to max_length characters."""
    if len(value) <= max_length:
        return value
    return value[:max_length] + "[TRUNCATED]"


_REDACTION_MARKER = "[REMOVED]"


def apply_redaction(value: Any, strategy: RedactionStrategy) -> Any:
    """Apply a redaction strategy to a single value.

    Non-string values are converted to string before redaction.
    None values pass through unchanged.
    """
    if value is None:
        return None

    if strategy == RedactionStrategy.NONE:
        return value

    str_value = str(value) if not isinstance(value, str) else value

    if strategy == RedactionStrategy.HASH:
        return _hash_value(str_value)
    elif strategy == RedactionStrategy.MASK:
        return _mask_value(str_value)
    elif strategy == RedactionStrategy.REMOVE:
        return _REDACTION_MARKER
    elif strategy == RedactionStrategy.TRUNCATE:
        return _truncate_value(str_value)
    else:
        # Fail-closed: unknown strategy treated as HASH
        return _hash_value(str_value)


# ---------------------------------------------------------------------------
# Document-level redaction
# ---------------------------------------------------------------------------

def redact_document(
    artifact_name: str,
    document: Mapping[str, Any],
    *,
    max_level: ClassificationLevel = ClassificationLevel.INTERNAL,
    override_strategy: Optional[RedactionStrategy] = None,
) -> dict[str, Any]:
    """Redact a document based on field classifications.

    Fields classified above max_level are redacted.
    The override_strategy, if provided, is used instead of each field's
    configured strategy.

    Args:
        artifact_name: The artifact filename (e.g. "metadata.json")
        document: The document to redact (not mutated)
        max_level: Maximum classification level allowed in output.
                   Fields above this level are redacted.
        override_strategy: If set, overrides per-field redaction strategy.

    Returns:
        A new dict with redacted values.
    """
    level_order = {
        ClassificationLevel.PUBLIC: 0,
        ClassificationLevel.INTERNAL: 1,
        ClassificationLevel.CONFIDENTIAL: 2,
        ClassificationLevel.RESTRICTED: 3,
    }

    result: dict[str, Any] = {}
    for key, value in document.items():
        classification = classify_field(artifact_name, key)

        field_level = level_order.get(classification.level, 1)
        allowed_level = level_order.get(max_level, 1)

        if field_level > allowed_level:
            strategy = override_strategy if override_strategy is not None else classification.redaction
            result[key] = apply_redaction(value, strategy)
        else:
            # Recurse into nested dicts
            if isinstance(value, dict):
                result[key] = _redact_nested(
                    artifact_name, key, value,
                    max_level=max_level,
                    level_order=level_order,
                    override_strategy=override_strategy,
                )
            else:
                result[key] = value

    return result


def _redact_nested(
    artifact_name: str,
    parent_key: str,
    nested: Mapping[str, Any],
    *,
    max_level: ClassificationLevel,
    level_order: dict[ClassificationLevel, int],
    override_strategy: Optional[RedactionStrategy],
) -> dict[str, Any]:
    """Redact nested dict fields using parent.child notation for classification lookup."""
    result: dict[str, Any] = {}
    for key, value in nested.items():
        field_path = f"{parent_key}.{key}"
        classification = classify_field(artifact_name, field_path)

        field_level = level_order.get(classification.level, 1)
        allowed_level = level_order.get(max_level, 1)

        if field_level > allowed_level:
            strategy = override_strategy if override_strategy is not None else classification.redaction
            result[key] = apply_redaction(value, strategy)
        elif isinstance(value, dict):
            result[key] = _redact_nested(
                artifact_name, field_path, value,
                max_level=max_level,
                level_order=level_order,
                override_strategy=override_strategy,
            )
        else:
            result[key] = value
    return result


def redact_archive(
    documents: Mapping[str, Mapping[str, Any]],
    *,
    max_level: ClassificationLevel = ClassificationLevel.INTERNAL,
) -> dict[str, dict[str, Any]]:
    """Redact all documents in a run archive.

    Args:
        documents: Map of artifact_name -> document dict
        max_level: Maximum classification level allowed in output

    Returns:
        New dict with all documents redacted
    """
    return {
        name: redact_document(name, doc, max_level=max_level)
        for name, doc in documents.items()
    }


__all__ = [
    "apply_redaction",
    "redact_document",
    "redact_archive",
]
