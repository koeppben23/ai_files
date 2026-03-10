"""Failure Model — Formal domain model for audit failure classification and recovery.

This module formalizes the failure semantics that were previously implicit in
work_run_archive.py (lines 195-244) into a standalone, testable domain model.

The failure model defines:
    - Failure categories with severity levels
    - Recovery strategies per failure type
    - Failure report generation (machine-readable)
    - Fail-closed policy enforcement

Contract version: FAILURE_MODEL.v1

Design:
    - Frozen dataclasses for immutable failure records
    - Pure functions (no I/O)
    - Fail-closed: unrecognized failures escalate to FATAL
    - Zero external dependencies (stdlib only)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import FrozenSet, Mapping, Optional, Sequence


# ---------------------------------------------------------------------------
# Contract constants
# ---------------------------------------------------------------------------

CONTRACT_VERSION = "FAILURE_MODEL.v1"


class FailureSeverity(Enum):
    """Severity levels for audit failures, ordered by escalation."""
    WARN = "warn"
    ERROR = "error"
    FATAL = "fatal"


class FailureCategory(Enum):
    """Categories of audit failures recognized by the governance system."""
    ARCHIVE_WRITE_ERROR = "archive_write_error"
    INTEGRITY_CHECK_FAILED = "integrity_check_failed"
    MISSING_REQUIRED_ARTIFACT = "missing_required_artifact"
    SCHEMA_VALIDATION_FAILED = "schema_validation_failed"
    CHECKSUM_MISMATCH = "checksum_mismatch"
    TIMESTAMP_INVARIANT_VIOLATED = "timestamp_invariant_violated"
    CROSS_DOCUMENT_INCONSISTENCY = "cross_document_inconsistency"
    RUN_ID_MISMATCH = "run_id_mismatch"
    REPO_FINGERPRINT_MISMATCH = "repo_fingerprint_mismatch"
    FINALIZATION_GUARD_FAILED = "finalization_guard_failed"
    DUPLICATE_RUN_ARCHIVE = "duplicate_run_archive"
    ATOMIC_WRITE_FAILED = "atomic_write_failed"
    UNKNOWN = "unknown"


class RecoveryStrategy(Enum):
    """Recovery strategies available after a failure."""
    RETRY_BY_OVERWRITE = "retry_by_overwrite"
    MANUAL_INTERVENTION = "manual_intervention"
    ESCALATE_TO_OPERATOR = "escalate_to_operator"
    INVALIDATE_AND_REARCHIVE = "invalidate_and_rearchive"
    NO_RECOVERY = "no_recovery"


# ---------------------------------------------------------------------------
# Failure classification table
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class FailureClassification:
    """Defines how a specific failure category is handled."""
    category: FailureCategory
    severity: FailureSeverity
    recovery_strategy: RecoveryStrategy
    retryable: bool
    max_retries: int
    description: str


#: Master classification table — SSOT for failure handling
FAILURE_CLASSIFICATIONS: Mapping[FailureCategory, FailureClassification] = {
    FailureCategory.ARCHIVE_WRITE_ERROR: FailureClassification(
        category=FailureCategory.ARCHIVE_WRITE_ERROR,
        severity=FailureSeverity.FATAL,
        recovery_strategy=RecoveryStrategy.RETRY_BY_OVERWRITE,
        retryable=True,
        max_retries=1,
        description="Failed to write one or more archive artifacts to disk",
    ),
    FailureCategory.INTEGRITY_CHECK_FAILED: FailureClassification(
        category=FailureCategory.INTEGRITY_CHECK_FAILED,
        severity=FailureSeverity.FATAL,
        recovery_strategy=RecoveryStrategy.INVALIDATE_AND_REARCHIVE,
        retryable=True,
        max_retries=1,
        description="Post-write integrity verification failed",
    ),
    FailureCategory.MISSING_REQUIRED_ARTIFACT: FailureClassification(
        category=FailureCategory.MISSING_REQUIRED_ARTIFACT,
        severity=FailureSeverity.FATAL,
        recovery_strategy=RecoveryStrategy.INVALIDATE_AND_REARCHIVE,
        retryable=True,
        max_retries=1,
        description="A required artifact is missing from the archive",
    ),
    FailureCategory.SCHEMA_VALIDATION_FAILED: FailureClassification(
        category=FailureCategory.SCHEMA_VALIDATION_FAILED,
        severity=FailureSeverity.ERROR,
        recovery_strategy=RecoveryStrategy.MANUAL_INTERVENTION,
        retryable=False,
        max_retries=0,
        description="An artifact's schema field does not match the expected schema identifier",
    ),
    FailureCategory.CHECKSUM_MISMATCH: FailureClassification(
        category=FailureCategory.CHECKSUM_MISMATCH,
        severity=FailureSeverity.FATAL,
        recovery_strategy=RecoveryStrategy.INVALIDATE_AND_REARCHIVE,
        retryable=True,
        max_retries=1,
        description="Computed checksum does not match the recorded checksum",
    ),
    FailureCategory.TIMESTAMP_INVARIANT_VIOLATED: FailureClassification(
        category=FailureCategory.TIMESTAMP_INVARIANT_VIOLATED,
        severity=FailureSeverity.ERROR,
        recovery_strategy=RecoveryStrategy.MANUAL_INTERVENTION,
        retryable=False,
        max_retries=0,
        description="Timestamp format or monotonicity invariant violated",
    ),
    FailureCategory.CROSS_DOCUMENT_INCONSISTENCY: FailureClassification(
        category=FailureCategory.CROSS_DOCUMENT_INCONSISTENCY,
        severity=FailureSeverity.FATAL,
        recovery_strategy=RecoveryStrategy.INVALIDATE_AND_REARCHIVE,
        retryable=True,
        max_retries=1,
        description="Cross-document fields (run_id, repo, timestamps) are inconsistent",
    ),
    FailureCategory.RUN_ID_MISMATCH: FailureClassification(
        category=FailureCategory.RUN_ID_MISMATCH,
        severity=FailureSeverity.FATAL,
        recovery_strategy=RecoveryStrategy.INVALIDATE_AND_REARCHIVE,
        retryable=False,
        max_retries=0,
        description="run_id in artifact does not match directory name",
    ),
    FailureCategory.REPO_FINGERPRINT_MISMATCH: FailureClassification(
        category=FailureCategory.REPO_FINGERPRINT_MISMATCH,
        severity=FailureSeverity.FATAL,
        recovery_strategy=RecoveryStrategy.MANUAL_INTERVENTION,
        retryable=False,
        max_retries=0,
        description="repo_fingerprint mismatch across archive documents",
    ),
    FailureCategory.FINALIZATION_GUARD_FAILED: FailureClassification(
        category=FailureCategory.FINALIZATION_GUARD_FAILED,
        severity=FailureSeverity.FATAL,
        recovery_strategy=RecoveryStrategy.RETRY_BY_OVERWRITE,
        retryable=True,
        max_retries=1,
        description="Run archive failed finalization guards after assembly",
    ),
    FailureCategory.DUPLICATE_RUN_ARCHIVE: FailureClassification(
        category=FailureCategory.DUPLICATE_RUN_ARCHIVE,
        severity=FailureSeverity.ERROR,
        recovery_strategy=RecoveryStrategy.MANUAL_INTERVENTION,
        retryable=False,
        max_retries=0,
        description="Attempted to create a run archive that already exists with non-failed status",
    ),
    FailureCategory.ATOMIC_WRITE_FAILED: FailureClassification(
        category=FailureCategory.ATOMIC_WRITE_FAILED,
        severity=FailureSeverity.FATAL,
        recovery_strategy=RecoveryStrategy.RETRY_BY_OVERWRITE,
        retryable=True,
        max_retries=5,
        description="Atomic file write (temp + rename) failed due to OS-level error",
    ),
    FailureCategory.UNKNOWN: FailureClassification(
        category=FailureCategory.UNKNOWN,
        severity=FailureSeverity.FATAL,
        recovery_strategy=RecoveryStrategy.ESCALATE_TO_OPERATOR,
        retryable=False,
        max_retries=0,
        description="Unrecognized failure — fail-closed escalation to operator",
    ),
}


# ---------------------------------------------------------------------------
# Failure report model
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class FailureDetail:
    """A single failure event within a failure report."""
    category: FailureCategory
    severity: FailureSeverity
    message: str
    artifact: str = ""
    field_path: str = ""
    expected: str = ""
    actual: str = ""


@dataclass(frozen=True)
class RecoveryAction:
    """A recommended recovery action."""
    strategy: RecoveryStrategy
    description: str
    retryable: bool
    max_retries: int


@dataclass(frozen=True)
class FailureReport:
    """Complete failure report for a run archive operation.

    Immutable record suitable for persistence as failure_report.json.
    """
    schema: str = "governance.failure-report.v1"
    contract_version: str = CONTRACT_VERSION
    run_id: str = ""
    repo_fingerprint: str = ""
    observed_at: str = ""
    overall_severity: FailureSeverity = FailureSeverity.FATAL
    failures: tuple[FailureDetail, ...] = ()
    recovery_actions: tuple[RecoveryAction, ...] = ()
    is_recoverable: bool = False


# ---------------------------------------------------------------------------
# Pure functions
# ---------------------------------------------------------------------------

def classify_failure(error_message: str) -> FailureCategory:
    """Classify an error message into a failure category.

    Uses keyword matching against known failure patterns.
    Falls back to UNKNOWN (fail-closed).
    """
    msg = error_message.lower()

    if "checksum mismatch" in msg or "checksum" in msg and "mismatch" in msg:
        return FailureCategory.CHECKSUM_MISMATCH
    if "missing run artifacts" in msg or "missing-required-artifact" in msg:
        return FailureCategory.MISSING_REQUIRED_ARTIFACT
    if "integrity" in msg and ("failed" in msg or "verify" in msg):
        return FailureCategory.INTEGRITY_CHECK_FAILED
    if "schema" in msg and ("mismatch" in msg or "invalid" in msg):
        return FailureCategory.SCHEMA_VALIDATION_FAILED
    if "run_id mismatch" in msg:
        return FailureCategory.RUN_ID_MISMATCH
    if "repo_fingerprint mismatch" in msg or "fingerprint" in msg and "mismatch" in msg:
        return FailureCategory.REPO_FINGERPRINT_MISMATCH
    if "materialized_at" in msg or "archived_at" in msg or "finalized_at" in msg:
        if "mismatch" in msg or "format" in msg:
            return FailureCategory.TIMESTAMP_INVARIANT_VIOLATED
    if "already exists" in msg:
        return FailureCategory.DUPLICATE_RUN_ARCHIVE
    if "finalization guards" in msg:
        return FailureCategory.FINALIZATION_GUARD_FAILED
    if "atomic" in msg or "replace" in msg or "write" in msg and "failed" in msg:
        return FailureCategory.ATOMIC_WRITE_FAILED
    if "archive" in msg and ("error" in msg or "failed" in msg):
        return FailureCategory.ARCHIVE_WRITE_ERROR

    return FailureCategory.UNKNOWN


def get_classification(category: FailureCategory) -> FailureClassification:
    """Get the classification for a failure category.

    Falls back to UNKNOWN classification (fail-closed).
    """
    return FAILURE_CLASSIFICATIONS.get(category, FAILURE_CLASSIFICATIONS[FailureCategory.UNKNOWN])


def build_failure_detail(
    *,
    error_message: str,
    artifact: str = "",
    field_path: str = "",
    expected: str = "",
    actual: str = "",
) -> FailureDetail:
    """Build a FailureDetail from an error message with automatic classification."""
    category = classify_failure(error_message)
    classification = get_classification(category)
    return FailureDetail(
        category=category,
        severity=classification.severity,
        message=error_message,
        artifact=artifact,
        field_path=field_path,
        expected=expected,
        actual=actual,
    )


def build_recovery_action(category: FailureCategory) -> RecoveryAction:
    """Build a RecoveryAction for a given failure category."""
    classification = get_classification(category)
    return RecoveryAction(
        strategy=classification.recovery_strategy,
        description=classification.description,
        retryable=classification.retryable,
        max_retries=classification.max_retries,
    )


def compute_overall_severity(failures: Sequence[FailureDetail]) -> FailureSeverity:
    """Compute the highest severity across all failures.

    Empty list returns WARN. Fail-closed: any FATAL escalates the whole report.
    """
    if not failures:
        return FailureSeverity.WARN

    severity_order = {FailureSeverity.WARN: 0, FailureSeverity.ERROR: 1, FailureSeverity.FATAL: 2}
    max_severity = FailureSeverity.WARN
    for f in failures:
        if severity_order.get(f.severity, 2) > severity_order.get(max_severity, 0):
            max_severity = f.severity
    return max_severity


def build_failure_report(
    *,
    run_id: str,
    repo_fingerprint: str,
    observed_at: str,
    error_messages: Sequence[str],
) -> FailureReport:
    """Build a complete failure report from a list of error messages.

    Each error message is classified, and recovery actions are deduced.
    """
    details: list[FailureDetail] = []
    seen_categories: set[FailureCategory] = set()

    for msg in error_messages:
        detail = build_failure_detail(error_message=msg)
        details.append(detail)
        seen_categories.add(detail.category)

    recovery_actions: list[RecoveryAction] = []
    for cat in sorted(seen_categories, key=lambda c: c.value):
        recovery_actions.append(build_recovery_action(cat))

    overall = compute_overall_severity(details)
    is_recoverable = all(
        get_classification(d.category).retryable for d in details
    )

    return FailureReport(
        run_id=run_id,
        repo_fingerprint=repo_fingerprint,
        observed_at=observed_at,
        overall_severity=overall,
        failures=tuple(details),
        recovery_actions=tuple(recovery_actions),
        is_recoverable=is_recoverable,
    )


def failure_report_to_dict(report: FailureReport) -> dict[str, object]:
    """Serialize a FailureReport to a JSON-compatible dict."""
    return {
        "schema": report.schema,
        "contract_version": report.contract_version,
        "run_id": report.run_id,
        "repo_fingerprint": report.repo_fingerprint,
        "observed_at": report.observed_at,
        "overall_severity": report.overall_severity.value,
        "is_recoverable": report.is_recoverable,
        "failures": [
            {
                "category": f.category.value,
                "severity": f.severity.value,
                "message": f.message,
                "artifact": f.artifact,
                "field_path": f.field_path,
                "expected": f.expected,
                "actual": f.actual,
            }
            for f in report.failures
        ],
        "recovery_actions": [
            {
                "strategy": a.strategy.value,
                "description": a.description,
                "retryable": a.retryable,
                "max_retries": a.max_retries,
            }
            for a in report.recovery_actions
        ],
    }


__all__ = [
    "CONTRACT_VERSION",
    "FailureSeverity",
    "FailureCategory",
    "RecoveryStrategy",
    "FailureClassification",
    "FailureDetail",
    "RecoveryAction",
    "FailureReport",
    "FAILURE_CLASSIFICATIONS",
    "classify_failure",
    "get_classification",
    "build_failure_detail",
    "build_recovery_action",
    "compute_overall_severity",
    "build_failure_report",
    "failure_report_to_dict",
]
