"""Deterministic exception-to-reason routing helpers."""

from __future__ import annotations


def canonicalize_reason_payload_failure(exc: Exception) -> tuple[str, str]:
    """Map payload builder failures to deterministic, non-leaking buckets."""

    message = str(exc)
    if isinstance(exc, ValueError) and message.startswith("invalid reason payload:"):
        return ("reason_payload_invalid", "schema_or_contract_violation")
    if isinstance(exc, ValueError) and "reason_schema_missing:" in message:
        return ("reason_schema_missing", "embedded_or_disk_schema_missing")
    if isinstance(exc, ValueError) and "reason_schema_invalid:" in message:
        return ("reason_schema_invalid", "schema_not_object")
    if isinstance(exc, ValueError) and "reason_registry_" in message:
        return ("reason_registry_invalid", "registry_unavailable_or_invalid")
    return ("reason_payload_build_failed", "unexpected_builder_error")
