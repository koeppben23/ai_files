"""Audit Storage Contract — Formal domain model for regulated audit guarantees.

This module formalizes the audit storage contract that was previously implicit
across run_audit_artifacts.py, io_verify.py, and work_run_archive.py into a
standalone, testable domain model.

Contract version: AUDIT_STORAGE_CONTRACT.v1

Design:
    - Frozen dataclasses for immutable contract records
    - Pure functions for validation (no I/O)
    - Fail-closed: any violation returns explicit error codes
    - Zero external dependencies (stdlib only + governance.domain)
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import FrozenSet, Mapping, Optional, Sequence, Tuple


# ---------------------------------------------------------------------------
# Contract constants
# ---------------------------------------------------------------------------

CONTRACT_VERSION = "AUDIT_STORAGE_CONTRACT.v1"

#: Allowed run lifecycle statuses — SSOT from run_audit_artifacts.RUN_STATUSES
ALLOWED_RUN_STATUSES: FrozenSet[str] = frozenset({
    "in_progress", "materialized", "finalized", "failed", "invalidated",
})

#: Allowed record lifecycle statuses — SSOT from run_audit_artifacts.RECORD_STATUSES
ALLOWED_RECORD_STATUSES: FrozenSet[str] = frozenset({
    "draft", "finalized", "superseded", "invalidated",
})

#: Allowed archive lifecycle statuses
ALLOWED_ARCHIVE_STATUSES: FrozenSet[str] = frozenset({
    "materialized", "finalized", "failed",
})

#: Allowed run types
ALLOWED_RUN_TYPES: FrozenSet[str] = frozenset({
    "analysis", "plan", "pr",
})

#: Allowed integrity statuses
ALLOWED_INTEGRITY_STATUSES: FrozenSet[str] = frozenset({
    "pending", "passed", "failed",
})

#: Required files in every finalized run archive
REQUIRED_ARCHIVE_FILES: FrozenSet[str] = frozenset({
    "SESSION_STATE.json",
    "metadata.json",
    "run-manifest.json",
    "provenance-record.json",
    "ticket-record.json",
    "review-decision-record.json",
    "outcome-record.json",
    "evidence-index.json",
    "checksums.json",
})

#: Optional files that may be present in a run archive
OPTIONAL_ARCHIVE_FILES: FrozenSet[str] = frozenset({
    "plan-record.json",
    "pr-record.json",
    "finalization-record.json",
})

#: All allowed files in a run archive (required + optional)
ALLOWED_ARCHIVE_FILES: FrozenSet[str] = REQUIRED_ARCHIVE_FILES | OPTIONAL_ARCHIVE_FILES

#: Expected schema identifiers per artifact
EXPECTED_SCHEMAS: Mapping[str, str] = {
    "run-manifest.json": "governance.run-manifest.v1",
    "metadata.json": "governance.work-run.snapshot.v2",
    "provenance-record.json": "governance.provenance-record.v1",
    "ticket-record.json": "governance.ticket-record.v1",
    "review-decision-record.json": "governance.review-decision-record.v1",
    "outcome-record.json": "governance.outcome-record.v1",
    "evidence-index.json": "governance.evidence-index.v1",
    "finalization-record.json": "governance.finalization-record.v1",
    "checksums.json": "governance.run-checksums.v1",
    "repository-manifest.json": "governance.repository-manifest.v1",
}

#: Required keys in the required_artifacts map of a run manifest
REQUIRED_ARTIFACT_KEYS: FrozenSet[str] = frozenset({
    "session_state", "run_manifest", "metadata",
    "ticket_record", "review_decision_record", "outcome_record", "evidence_index",
    "provenance", "plan_record", "pr_record", "checksums",
})

#: Artifact keys that must always be True in required_artifacts
BASELINE_REQUIRED_TRUE: FrozenSet[str] = frozenset({
    "session_state", "run_manifest", "metadata", "ticket_record", "review_decision_record",
    "outcome_record", "evidence_index", "provenance", "checksums",
})

#: Required keys in the archived_files map of metadata
REQUIRED_ARCHIVED_FILE_KEYS: FrozenSet[str] = frozenset({
    "session_state", "plan_record", "pr_record",
    "ticket_record", "review_decision_record", "outcome_record", "evidence_index",
    "run_manifest", "provenance_record", "checksums",
})

#: Archived file keys that must always be True
BASELINE_ARCHIVED_TRUE: FrozenSet[str] = frozenset({
    "session_state", "ticket_record", "review_decision_record", "outcome_record", "evidence_index",
    "run_manifest", "provenance_record", "checksums",
})

_RFC3339_UTC_Z_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
_REPO_FINGERPRINT_RE = re.compile(r"^[0-9a-f]{24}$")
_SHA256_PREFIXED_RE = re.compile(r"^sha256:[0-9a-f]{64}$")


# ---------------------------------------------------------------------------
# Frozen domain models
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class AuditContractViolation:
    """Single contract violation with machine-readable code and human message."""
    code: str
    message: str
    path: str = ""


@dataclass(frozen=True)
class RunLifecycleInvariant:
    """Describes the expected state invariants for a given run_status."""
    run_status: str
    expected_record_status: Optional[str]
    expected_integrity_status: Optional[str]
    requires_finalized_at: bool
    forbids_finalized_at: bool
    requires_finalization_errors: bool
    forbids_finalization_errors: bool


#: Lifecycle invariant table — defines what each run_status requires/forbids
LIFECYCLE_INVARIANTS: Mapping[str, RunLifecycleInvariant] = {
    "finalized": RunLifecycleInvariant(
        run_status="finalized",
        expected_record_status="finalized",
        expected_integrity_status="passed",
        requires_finalized_at=True,
        forbids_finalized_at=False,
        requires_finalization_errors=False,
        forbids_finalization_errors=True,
    ),
    "failed": RunLifecycleInvariant(
        run_status="failed",
        expected_record_status="invalidated",
        expected_integrity_status="failed",
        requires_finalized_at=False,
        forbids_finalized_at=True,
        requires_finalization_errors=True,
        forbids_finalization_errors=False,
    ),
    "materialized": RunLifecycleInvariant(
        run_status="materialized",
        expected_record_status=None,
        expected_integrity_status="pending",
        requires_finalized_at=False,
        forbids_finalized_at=True,
        requires_finalization_errors=False,
        forbids_finalization_errors=False,
    ),
}


@dataclass(frozen=True)
class RunTypeArtifactRule:
    """Describes artifact requirements for a given run_type."""
    run_type: str
    plan_record_required: bool
    pr_record_required: bool


#: Run type artifact rules — which optional artifacts each run_type requires
RUN_TYPE_ARTIFACT_RULES: Mapping[str, RunTypeArtifactRule] = {
    "analysis": RunTypeArtifactRule(run_type="analysis", plan_record_required=False, pr_record_required=False),
    "plan": RunTypeArtifactRule(run_type="plan", plan_record_required=True, pr_record_required=False),
    "pr": RunTypeArtifactRule(run_type="pr", plan_record_required=False, pr_record_required=True),
}


# ---------------------------------------------------------------------------
# Pure validation functions
# ---------------------------------------------------------------------------

def validate_repo_fingerprint(value: str) -> list[AuditContractViolation]:
    """Validate a repo fingerprint string."""
    if not isinstance(value, str) or not _REPO_FINGERPRINT_RE.match(value):
        return [AuditContractViolation(
            code="INVALID_REPO_FINGERPRINT",
            message=f"Expected 24-char hex string, got: {value!r}",
            path="repo_fingerprint",
        )]
    return []


def validate_timestamp(value: object, field_name: str) -> list[AuditContractViolation]:
    """Validate an RFC3339 UTC Z timestamp string."""
    if not isinstance(value, str) or not _RFC3339_UTC_Z_RE.match(value.strip()):
        return [AuditContractViolation(
            code="INVALID_TIMESTAMP",
            message=f"Expected RFC3339 UTC Z timestamp for {field_name}, got: {value!r}",
            path=field_name,
        )]
    return []


def validate_checksum_digest(value: object, field_name: str) -> list[AuditContractViolation]:
    """Validate a sha256-prefixed digest string."""
    if not isinstance(value, str) or not _SHA256_PREFIXED_RE.match(value):
        return [AuditContractViolation(
            code="INVALID_CHECKSUM_DIGEST",
            message=f"Expected sha256:<64hex> for {field_name}, got: {value!r}",
            path=field_name,
        )]
    return []


def validate_run_lifecycle_invariants(
    *,
    run_status: str,
    record_status: str,
    integrity_status: str,
    finalized_at: object,
    finalization_errors: object,
) -> list[AuditContractViolation]:
    """Validate that run status, record status, and integrity are consistent.

    Enforces the lifecycle invariant table (LIFECYCLE_INVARIANTS).
    """
    violations: list[AuditContractViolation] = []

    if run_status not in ALLOWED_RUN_STATUSES:
        violations.append(AuditContractViolation(
            code="INVALID_RUN_STATUS",
            message=f"run_status '{run_status}' not in allowed set",
            path="run_status",
        ))
        return violations

    invariant = LIFECYCLE_INVARIANTS.get(run_status)
    if invariant is None:
        return violations

    if invariant.expected_record_status is not None and record_status != invariant.expected_record_status:
        violations.append(AuditContractViolation(
            code="RECORD_STATUS_MISMATCH",
            message=f"run_status={run_status} requires record_status={invariant.expected_record_status}, got {record_status}",
            path="record_status",
        ))

    if invariant.expected_integrity_status is not None and integrity_status != invariant.expected_integrity_status:
        violations.append(AuditContractViolation(
            code="INTEGRITY_STATUS_MISMATCH",
            message=f"run_status={run_status} requires integrity_status={invariant.expected_integrity_status}, got {integrity_status}",
            path="integrity_status",
        ))

    has_finalized_at = isinstance(finalized_at, str) and finalized_at.strip()
    if invariant.requires_finalized_at and not has_finalized_at:
        violations.append(AuditContractViolation(
            code="MISSING_FINALIZED_AT",
            message=f"run_status={run_status} requires finalized_at",
            path="finalized_at",
        ))
    if invariant.forbids_finalized_at and has_finalized_at:
        violations.append(AuditContractViolation(
            code="UNEXPECTED_FINALIZED_AT",
            message=f"run_status={run_status} must not have finalized_at",
            path="finalized_at",
        ))

    has_errors = isinstance(finalization_errors, list) and len(finalization_errors) > 0
    if invariant.requires_finalization_errors and not has_errors:
        violations.append(AuditContractViolation(
            code="MISSING_FINALIZATION_ERRORS",
            message=f"run_status={run_status} requires non-empty finalization_errors",
            path="finalization_errors",
        ))
    if invariant.forbids_finalization_errors and finalization_errors is not None:
        violations.append(AuditContractViolation(
            code="UNEXPECTED_FINALIZATION_ERRORS",
            message=f"run_status={run_status} must not include finalization_errors",
            path="finalization_errors",
        ))

    return violations


def validate_run_type_artifacts(
    *,
    run_type: str,
    plan_record_required: bool,
    pr_record_required: bool,
    plan_record_archived: bool,
    pr_record_archived: bool,
) -> list[AuditContractViolation]:
    """Validate that run_type artifact requirements are met."""
    violations: list[AuditContractViolation] = []

    if run_type not in ALLOWED_RUN_TYPES:
        violations.append(AuditContractViolation(
            code="INVALID_RUN_TYPE",
            message=f"run_type '{run_type}' not in allowed set",
            path="run_type",
        ))
        return violations

    rule = RUN_TYPE_ARTIFACT_RULES[run_type]

    if rule.plan_record_required != plan_record_required:
        violations.append(AuditContractViolation(
            code="PLAN_RECORD_REQUIRED_MISMATCH",
            message=f"run_type={run_type} expects plan_record_required={rule.plan_record_required}",
            path="required_artifacts.plan_record",
        ))

    if rule.pr_record_required != pr_record_required:
        violations.append(AuditContractViolation(
            code="PR_RECORD_REQUIRED_MISMATCH",
            message=f"run_type={run_type} expects pr_record_required={rule.pr_record_required}",
            path="required_artifacts.pr_record",
        ))

    if plan_record_required and not plan_record_archived:
        violations.append(AuditContractViolation(
            code="REQUIRED_PLAN_NOT_ARCHIVED",
            message="plan_record is required but was not archived",
            path="archived_files.plan_record",
        ))

    if pr_record_required and not pr_record_archived:
        violations.append(AuditContractViolation(
            code="REQUIRED_PR_NOT_ARCHIVED",
            message="pr_record is required but was not archived",
            path="archived_files.pr_record",
        ))

    return violations


def validate_cross_document_consistency(
    *,
    manifest_run_id: str,
    metadata_run_id: str,
    provenance_run_id: str,
    directory_run_id: str,
    manifest_repo: str,
    metadata_repo: str,
    provenance_repo: str,
    manifest_materialized_at: str,
    metadata_archived_at: str,
    provenance_materialized_at: str,
) -> list[AuditContractViolation]:
    """Validate cross-document consistency between manifest, metadata, and provenance."""
    violations: list[AuditContractViolation] = []

    # run_id consistency
    if manifest_run_id != directory_run_id:
        violations.append(AuditContractViolation(
            code="RUN_ID_MISMATCH_MANIFEST",
            message=f"manifest run_id={manifest_run_id} != directory={directory_run_id}",
            path="run-manifest.json/run_id",
        ))
    if metadata_run_id != directory_run_id:
        violations.append(AuditContractViolation(
            code="RUN_ID_MISMATCH_METADATA",
            message=f"metadata run_id={metadata_run_id} != directory={directory_run_id}",
            path="metadata.json/run_id",
        ))
    if provenance_run_id != directory_run_id:
        violations.append(AuditContractViolation(
            code="RUN_ID_MISMATCH_PROVENANCE",
            message=f"provenance run_id={provenance_run_id} != directory={directory_run_id}",
            path="provenance-record.json/run_id",
        ))

    # repo_fingerprint consistency
    if not manifest_repo or manifest_repo != metadata_repo or metadata_repo != provenance_repo:
        violations.append(AuditContractViolation(
            code="REPO_FINGERPRINT_MISMATCH",
            message="repo_fingerprint inconsistent across manifest/metadata/provenance",
            path="repo_fingerprint",
        ))

    # timestamp consistency
    if manifest_materialized_at != metadata_archived_at:
        violations.append(AuditContractViolation(
            code="TIMESTAMP_MISMATCH_MANIFEST_METADATA",
            message="materialized_at/archived_at mismatch between manifest and metadata",
            path="materialized_at",
        ))
    if manifest_materialized_at != provenance_materialized_at:
        violations.append(AuditContractViolation(
            code="TIMESTAMP_MISMATCH_MANIFEST_PROVENANCE",
            message="materialized_at mismatch between manifest and provenance",
            path="timestamps.materialized_at",
        ))

    return violations


def validate_required_artifact_keys(
    required_artifacts: Mapping[str, object],
) -> list[AuditContractViolation]:
    """Validate the required_artifacts map has the correct keys and baseline values."""
    violations: list[AuditContractViolation] = []

    keys = set(required_artifacts.keys())
    if keys != REQUIRED_ARTIFACT_KEYS:
        missing = sorted(REQUIRED_ARTIFACT_KEYS - keys)
        extra = sorted(keys - REQUIRED_ARTIFACT_KEYS)
        violations.append(AuditContractViolation(
            code="REQUIRED_ARTIFACTS_KEY_MISMATCH",
            message=f"missing={missing}, extra={extra}",
            path="required_artifacts",
        ))

    for key in BASELINE_REQUIRED_TRUE:
        if required_artifacts.get(key) is not True:
            violations.append(AuditContractViolation(
                code="BASELINE_ARTIFACT_NOT_TRUE",
                message=f"required_artifacts.{key} must be true",
                path=f"required_artifacts.{key}",
            ))

    return violations


def validate_archived_file_keys(
    archived_files: Mapping[str, object],
) -> list[AuditContractViolation]:
    """Validate the archived_files map has the correct keys and baseline values."""
    violations: list[AuditContractViolation] = []

    keys = set(archived_files.keys())
    if keys != REQUIRED_ARCHIVED_FILE_KEYS:
        missing = sorted(REQUIRED_ARCHIVED_FILE_KEYS - keys)
        extra = sorted(keys - REQUIRED_ARCHIVED_FILE_KEYS)
        violations.append(AuditContractViolation(
            code="ARCHIVED_FILES_KEY_MISMATCH",
            message=f"missing={missing}, extra={extra}",
            path="archived_files",
        ))

    for key in BASELINE_ARCHIVED_TRUE:
        if archived_files.get(key) is not True:
            violations.append(AuditContractViolation(
                code="BASELINE_ARCHIVED_NOT_TRUE",
                message=f"archived_files.{key} must be true",
                path=f"archived_files.{key}",
            ))

    for key, value in archived_files.items():
        if not isinstance(key, str) or not isinstance(value, bool):
            violations.append(AuditContractViolation(
                code="ARCHIVED_FILES_INVALID_ENTRY",
                message=f"archived_files entry {key!r} has non-bool value",
                path=f"archived_files.{key}",
            ))

    return violations


def validate_schema_identifier(
    artifact_name: str,
    actual_schema: str,
) -> list[AuditContractViolation]:
    """Validate that an artifact's schema field matches the expected value."""
    expected = EXPECTED_SCHEMAS.get(artifact_name)
    if expected is None:
        return []
    if actual_schema != expected:
        return [AuditContractViolation(
            code="SCHEMA_MISMATCH",
            message=f"{artifact_name}: expected schema={expected}, got {actual_schema}",
            path=f"{artifact_name}/schema",
        )]
    return []


def get_contract_summary() -> dict[str, object]:
    """Return a machine-readable summary of the audit contract for documentation/tooling."""
    return {
        "contract_version": CONTRACT_VERSION,
        "allowed_run_statuses": sorted(ALLOWED_RUN_STATUSES),
        "allowed_record_statuses": sorted(ALLOWED_RECORD_STATUSES),
        "allowed_archive_statuses": sorted(ALLOWED_ARCHIVE_STATUSES),
        "allowed_run_types": sorted(ALLOWED_RUN_TYPES),
        "allowed_integrity_statuses": sorted(ALLOWED_INTEGRITY_STATUSES),
        "required_archive_files": sorted(REQUIRED_ARCHIVE_FILES),
        "optional_archive_files": sorted(OPTIONAL_ARCHIVE_FILES),
        "expected_schemas": dict(EXPECTED_SCHEMAS),
        "required_artifact_keys": sorted(REQUIRED_ARTIFACT_KEYS),
        "baseline_required_true": sorted(BASELINE_REQUIRED_TRUE),
        "required_archived_file_keys": sorted(REQUIRED_ARCHIVED_FILE_KEYS),
        "baseline_archived_true": sorted(BASELINE_ARCHIVED_TRUE),
        "lifecycle_invariants": {
            status: {
                "expected_record_status": inv.expected_record_status,
                "expected_integrity_status": inv.expected_integrity_status,
                "requires_finalized_at": inv.requires_finalized_at,
                "forbids_finalized_at": inv.forbids_finalized_at,
                "requires_finalization_errors": inv.requires_finalization_errors,
                "forbids_finalization_errors": inv.forbids_finalization_errors,
            }
            for status, inv in LIFECYCLE_INVARIANTS.items()
        },
        "run_type_artifact_rules": {
            rt: {
                "plan_record_required": rule.plan_record_required,
                "pr_record_required": rule.pr_record_required,
            }
            for rt, rule in RUN_TYPE_ARTIFACT_RULES.items()
        },
    }


__all__ = [
    "CONTRACT_VERSION",
    "ALLOWED_RUN_STATUSES",
    "ALLOWED_RECORD_STATUSES",
    "ALLOWED_ARCHIVE_STATUSES",
    "ALLOWED_RUN_TYPES",
    "ALLOWED_INTEGRITY_STATUSES",
    "REQUIRED_ARCHIVE_FILES",
    "OPTIONAL_ARCHIVE_FILES",
    "ALLOWED_ARCHIVE_FILES",
    "EXPECTED_SCHEMAS",
    "REQUIRED_ARTIFACT_KEYS",
    "BASELINE_REQUIRED_TRUE",
    "REQUIRED_ARCHIVED_FILE_KEYS",
    "BASELINE_ARCHIVED_TRUE",
    "LIFECYCLE_INVARIANTS",
    "RUN_TYPE_ARTIFACT_RULES",
    "AuditContractViolation",
    "RunLifecycleInvariant",
    "RunTypeArtifactRule",
    "validate_repo_fingerprint",
    "validate_timestamp",
    "validate_checksum_digest",
    "validate_run_lifecycle_invariants",
    "validate_run_type_artifacts",
    "validate_cross_document_consistency",
    "validate_required_artifact_keys",
    "validate_archived_file_keys",
    "validate_schema_identifier",
    "get_contract_summary",
]
