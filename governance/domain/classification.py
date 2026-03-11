"""Data Classification — Domain model for field-level data classification.

Provides classification labels for all data fields that appear in audit artifacts,
enabling regulated customers to understand what data sensitivity level each field
carries and what redaction rules apply during export.

Contract version: DATA_CLASSIFICATION.v1

Design:
    - Frozen dataclasses for immutable classification records
    - Pure functions (no I/O)
    - Fail-closed: unclassified fields default to INTERNAL
    - Zero external dependencies (stdlib only)
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import FrozenSet, Mapping, Optional, Sequence


# ---------------------------------------------------------------------------
# Contract constants
# ---------------------------------------------------------------------------

CONTRACT_VERSION = "DATA_CLASSIFICATION.v1"


class ClassificationLevel(Enum):
    """Data classification levels, ordered by sensitivity (ascending)."""
    PUBLIC = "public"
    INTERNAL = "internal"
    CONFIDENTIAL = "confidential"
    RESTRICTED = "restricted"


class RedactionStrategy(Enum):
    """How a field should be redacted during export."""
    NONE = "none"
    HASH = "hash"
    MASK = "mask"
    REMOVE = "remove"
    TRUNCATE = "truncate"


# ---------------------------------------------------------------------------
# Classification records
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class FieldClassification:
    """Classification metadata for a single field."""
    field_path: str
    artifact: str
    level: ClassificationLevel
    redaction: RedactionStrategy
    description: str
    pii: bool = False
    audit_relevant: bool = True


# ---------------------------------------------------------------------------
# Field classification catalog — SSOT
# ---------------------------------------------------------------------------

#: All classified fields in audit artifacts, keyed by "artifact::field_path"
FIELD_CLASSIFICATIONS: Mapping[str, FieldClassification] = {
    # --- run-manifest.json ---
    "run-manifest.json::schema": FieldClassification(
        field_path="schema", artifact="run-manifest.json",
        level=ClassificationLevel.PUBLIC, redaction=RedactionStrategy.NONE,
        description="Schema identifier",
    ),
    "run-manifest.json::repo_fingerprint": FieldClassification(
        field_path="repo_fingerprint", artifact="run-manifest.json",
        level=ClassificationLevel.INTERNAL, redaction=RedactionStrategy.HASH,
        description="Repository identity hash (derived from remote URL)",
    ),
    "run-manifest.json::run_id": FieldClassification(
        field_path="run_id", artifact="run-manifest.json",
        level=ClassificationLevel.INTERNAL, redaction=RedactionStrategy.NONE,
        description="Unique run identifier",
    ),
    "run-manifest.json::run_type": FieldClassification(
        field_path="run_type", artifact="run-manifest.json",
        level=ClassificationLevel.PUBLIC, redaction=RedactionStrategy.NONE,
        description="Run type classification (analysis/plan/pr)",
    ),
    "run-manifest.json::materialized_at": FieldClassification(
        field_path="materialized_at", artifact="run-manifest.json",
        level=ClassificationLevel.INTERNAL, redaction=RedactionStrategy.NONE,
        description="Timestamp of run materialization",
    ),
    "run-manifest.json::run_status": FieldClassification(
        field_path="run_status", artifact="run-manifest.json",
        level=ClassificationLevel.PUBLIC, redaction=RedactionStrategy.NONE,
        description="Current run lifecycle status",
    ),
    "run-manifest.json::record_status": FieldClassification(
        field_path="record_status", artifact="run-manifest.json",
        level=ClassificationLevel.PUBLIC, redaction=RedactionStrategy.NONE,
        description="Current record lifecycle status",
    ),
    "run-manifest.json::integrity_status": FieldClassification(
        field_path="integrity_status", artifact="run-manifest.json",
        level=ClassificationLevel.PUBLIC, redaction=RedactionStrategy.NONE,
        description="Integrity verification status",
    ),

    # --- metadata.json ---
    "metadata.json::snapshot_digest": FieldClassification(
        field_path="snapshot_digest", artifact="metadata.json",
        level=ClassificationLevel.INTERNAL, redaction=RedactionStrategy.NONE,
        description="SHA-256 digest of session state snapshot",
    ),
    "metadata.json::ticket_digest": FieldClassification(
        field_path="ticket_digest", artifact="metadata.json",
        level=ClassificationLevel.CONFIDENTIAL, redaction=RedactionStrategy.HASH,
        description="Digest of ticket content (may reference customer requirements)",
    ),
    "metadata.json::plan_record_digest": FieldClassification(
        field_path="plan_record_digest", artifact="metadata.json",
        level=ClassificationLevel.CONFIDENTIAL, redaction=RedactionStrategy.HASH,
        description="Digest of implementation plan",
    ),
    "metadata.json::failure_reason": FieldClassification(
        field_path="failure_reason", artifact="metadata.json",
        level=ClassificationLevel.CONFIDENTIAL, redaction=RedactionStrategy.MASK,
        description="Error message from archive failure (may contain system paths)",
    ),

    # --- provenance-record.json ---
    "provenance-record.json::policy_fingerprint": FieldClassification(
        field_path="policy_fingerprint", artifact="provenance-record.json",
        level=ClassificationLevel.INTERNAL, redaction=RedactionStrategy.NONE,
        description="Hash of the active policy at materialization time",
    ),
    "provenance-record.json::launcher": FieldClassification(
        field_path="launcher", artifact="provenance-record.json",
        level=ClassificationLevel.PUBLIC, redaction=RedactionStrategy.NONE,
        description="Entrypoint that triggered the run",
    ),

    # --- SESSION_STATE.json ---
    "SESSION_STATE.json::session_run_id": FieldClassification(
        field_path="session_run_id", artifact="SESSION_STATE.json",
        level=ClassificationLevel.INTERNAL, redaction=RedactionStrategy.NONE,
        description="Session run identifier",
    ),
    "SESSION_STATE.json::Phase": FieldClassification(
        field_path="Phase", artifact="SESSION_STATE.json",
        level=ClassificationLevel.PUBLIC, redaction=RedactionStrategy.NONE,
        description="Current governance phase",
    ),
    "SESSION_STATE.json::PullRequestTitle": FieldClassification(
        field_path="PullRequestTitle", artifact="SESSION_STATE.json",
        level=ClassificationLevel.CONFIDENTIAL, redaction=RedactionStrategy.MASK,
        description="PR title (may contain customer-specific information)",
        pii=True,
    ),
    "SESSION_STATE.json::PullRequestBody": FieldClassification(
        field_path="PullRequestBody", artifact="SESSION_STATE.json",
        level=ClassificationLevel.RESTRICTED, redaction=RedactionStrategy.REMOVE,
        description="PR body (may contain detailed implementation plans, customer data references)",
        pii=True,
    ),
}

#: Default classification for unrecognized fields (fail-closed: INTERNAL)
DEFAULT_CLASSIFICATION = FieldClassification(
    field_path="<unknown>",
    artifact="<unknown>",
    level=ClassificationLevel.INTERNAL,
    redaction=RedactionStrategy.HASH,
    description="Unclassified field — default to INTERNAL with hash redaction",
)


# ---------------------------------------------------------------------------
# Pure functions
# ---------------------------------------------------------------------------

def classify_field(artifact: str, field_path: str) -> FieldClassification:
    """Classify a field within an artifact.

    Falls back to DEFAULT_CLASSIFICATION (fail-closed: INTERNAL + HASH).
    """
    key = f"{artifact}::{field_path}"
    return FIELD_CLASSIFICATIONS.get(key, DEFAULT_CLASSIFICATION)


def get_fields_by_level(level: ClassificationLevel) -> list[FieldClassification]:
    """Return all fields classified at a given level."""
    return [f for f in FIELD_CLASSIFICATIONS.values() if f.level == level]


def get_fields_requiring_redaction() -> list[FieldClassification]:
    """Return all fields that require redaction on export."""
    return [f for f in FIELD_CLASSIFICATIONS.values() if f.redaction != RedactionStrategy.NONE]


def get_pii_fields() -> list[FieldClassification]:
    """Return all fields marked as containing PII."""
    return [f for f in FIELD_CLASSIFICATIONS.values() if f.pii]


def get_classification_summary() -> dict[str, object]:
    """Return a machine-readable summary of the classification catalog."""
    by_level: dict[str, int] = {}
    by_redaction: dict[str, int] = {}
    for f in FIELD_CLASSIFICATIONS.values():
        by_level[f.level.value] = by_level.get(f.level.value, 0) + 1
        by_redaction[f.redaction.value] = by_redaction.get(f.redaction.value, 0) + 1
    return {
        "contract_version": CONTRACT_VERSION,
        "total_classified_fields": len(FIELD_CLASSIFICATIONS),
        "fields_by_level": by_level,
        "fields_by_redaction": by_redaction,
        "pii_fields_count": len(get_pii_fields()),
        "redaction_required_count": len(get_fields_requiring_redaction()),
    }


__all__ = [
    "CONTRACT_VERSION",
    "ClassificationLevel",
    "RedactionStrategy",
    "FieldClassification",
    "FIELD_CLASSIFICATIONS",
    "DEFAULT_CLASSIFICATION",
    "classify_field",
    "get_fields_by_level",
    "get_fields_requiring_redaction",
    "get_pii_fields",
    "get_classification_summary",
]
