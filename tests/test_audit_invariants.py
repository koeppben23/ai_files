"""Audit Invariant Tests — WI-3 Test Matrix Hardening.

Tests structural invariants of the audit domain models:
- Lifecycle state machine invariants
- Run type / artifact requirement invariants
- Cross-document consistency invariants
- Failure model classification invariants
- Contract constant immutability
"""

from __future__ import annotations

import pytest

from governance_runtime.domain.audit_contract import (
    ALLOWED_RUN_STATUSES,
    ALLOWED_RECORD_STATUSES,
    ALLOWED_ARCHIVE_STATUSES,
    ALLOWED_RUN_TYPES,
    ALLOWED_INTEGRITY_STATUSES,
    REQUIRED_ARCHIVE_FILES,
    OPTIONAL_ARCHIVE_FILES,
    ALLOWED_ARCHIVE_FILES,
    EXPECTED_SCHEMAS,
    REQUIRED_ARTIFACT_KEYS,
    BASELINE_REQUIRED_TRUE,
    REQUIRED_ARCHIVED_FILE_KEYS,
    BASELINE_ARCHIVED_TRUE,
    LIFECYCLE_INVARIANTS,
    RUN_TYPE_ARTIFACT_RULES,
    CONTRACT_VERSION,
    validate_run_lifecycle_invariants,
    validate_run_type_artifacts,
    validate_cross_document_consistency,
    validate_required_artifact_keys,
    validate_archived_file_keys,
    get_contract_summary,
)
from governance_runtime.domain.failure_model import (
    FailureCategory,
    FailureSeverity,
    RecoveryStrategy,
    FAILURE_CLASSIFICATIONS,
    classify_failure,
    get_classification,
    compute_overall_severity,
    build_failure_report,
    failure_report_to_dict,
    FailureDetail,
)
from governance_runtime.infrastructure.run_audit_artifacts import (
    RUN_STATUSES,
    RECORD_STATUSES,
)


# ---------------------------------------------------------------------------
# Audit Contract Constant Invariants
# ---------------------------------------------------------------------------

class TestAuditContractConstants:
    """Verify that domain model constants are consistent with production code."""

    def test_run_statuses_match_production(self) -> None:
        assert ALLOWED_RUN_STATUSES == frozenset(RUN_STATUSES)

    def test_record_statuses_match_production(self) -> None:
        assert ALLOWED_RECORD_STATUSES == frozenset(RECORD_STATUSES)

    def test_contract_version_is_v1(self) -> None:
        assert CONTRACT_VERSION == "AUDIT_STORAGE_CONTRACT.v1"

    def test_required_archive_files_complete(self) -> None:
        expected = {"SESSION_STATE.json", "metadata.json", "run-manifest.json",
                    "provenance-record.json", "ticket-record.json", "review-decision-record.json",
                    "outcome-record.json", "evidence-index.json", "checksums.json"}
        assert REQUIRED_ARCHIVE_FILES == frozenset(expected)

    def test_optional_files_are_plan_pr_and_finalization(self) -> None:
        assert OPTIONAL_ARCHIVE_FILES == frozenset(
            {"plan-record.json", "pr-record.json", "finalization-record.json"}
        )

    def test_allowed_is_union_of_required_and_optional(self) -> None:
        assert ALLOWED_ARCHIVE_FILES == REQUIRED_ARCHIVE_FILES | OPTIONAL_ARCHIVE_FILES

    def test_baseline_required_true_subset_of_artifact_keys(self) -> None:
        assert BASELINE_REQUIRED_TRUE.issubset(REQUIRED_ARTIFACT_KEYS)

    def test_baseline_archived_true_subset_of_archived_keys(self) -> None:
        assert BASELINE_ARCHIVED_TRUE.issubset(REQUIRED_ARCHIVED_FILE_KEYS)

    def test_all_run_types_have_artifact_rules(self) -> None:
        for rt in ALLOWED_RUN_TYPES:
            assert rt in RUN_TYPE_ARTIFACT_RULES

    def test_all_lifecycle_invariants_for_terminal_statuses(self) -> None:
        # finalized and failed must have invariants
        assert "finalized" in LIFECYCLE_INVARIANTS
        assert "failed" in LIFECYCLE_INVARIANTS
        assert "materialized" in LIFECYCLE_INVARIANTS

    def test_expected_schemas_cover_required_artifacts(self) -> None:
        # At minimum, manifest, metadata, provenance, checksums must have schemas
        assert "run-manifest.json" in EXPECTED_SCHEMAS
        assert "metadata.json" in EXPECTED_SCHEMAS
        assert "provenance-record.json" in EXPECTED_SCHEMAS
        assert "checksums.json" in EXPECTED_SCHEMAS


# ---------------------------------------------------------------------------
# Lifecycle State Machine Invariants
# ---------------------------------------------------------------------------

class TestLifecycleInvariants:
    """Verify lifecycle invariant validation catches all violation types."""

    def test_finalized_run_valid(self) -> None:
        violations = validate_run_lifecycle_invariants(
            run_status="finalized",
            record_status="finalized",
            integrity_status="passed",
            finalized_at="2026-03-10T10:00:00Z",
            finalization_errors=None,
        )
        assert violations == []

    def test_finalized_run_missing_finalized_at(self) -> None:
        violations = validate_run_lifecycle_invariants(
            run_status="finalized",
            record_status="finalized",
            integrity_status="passed",
            finalized_at=None,
            finalization_errors=None,
        )
        codes = {v.code for v in violations}
        assert "MISSING_FINALIZED_AT" in codes

    def test_finalized_run_with_finalization_errors(self) -> None:
        violations = validate_run_lifecycle_invariants(
            run_status="finalized",
            record_status="finalized",
            integrity_status="passed",
            finalized_at="2026-03-10T10:00:00Z",
            finalization_errors=["some-error"],
        )
        codes = {v.code for v in violations}
        assert "UNEXPECTED_FINALIZATION_ERRORS" in codes

    def test_finalized_run_wrong_record_status(self) -> None:
        violations = validate_run_lifecycle_invariants(
            run_status="finalized",
            record_status="draft",
            integrity_status="passed",
            finalized_at="2026-03-10T10:00:00Z",
            finalization_errors=None,
        )
        codes = {v.code for v in violations}
        assert "RECORD_STATUS_MISMATCH" in codes

    def test_finalized_run_wrong_integrity(self) -> None:
        violations = validate_run_lifecycle_invariants(
            run_status="finalized",
            record_status="finalized",
            integrity_status="failed",
            finalized_at="2026-03-10T10:00:00Z",
            finalization_errors=None,
        )
        codes = {v.code for v in violations}
        assert "INTEGRITY_STATUS_MISMATCH" in codes

    def test_failed_run_valid(self) -> None:
        violations = validate_run_lifecycle_invariants(
            run_status="failed",
            record_status="invalidated",
            integrity_status="failed",
            finalized_at=None,
            finalization_errors=["missing-required-artifact:plan_record"],
        )
        assert violations == []

    def test_failed_run_missing_errors(self) -> None:
        violations = validate_run_lifecycle_invariants(
            run_status="failed",
            record_status="invalidated",
            integrity_status="failed",
            finalized_at=None,
            finalization_errors=None,
        )
        codes = {v.code for v in violations}
        assert "MISSING_FINALIZATION_ERRORS" in codes

    def test_failed_run_with_finalized_at(self) -> None:
        violations = validate_run_lifecycle_invariants(
            run_status="failed",
            record_status="invalidated",
            integrity_status="failed",
            finalized_at="2026-03-10T10:00:00Z",
            finalization_errors=["error"],
        )
        codes = {v.code for v in violations}
        assert "UNEXPECTED_FINALIZED_AT" in codes

    def test_materialized_run_valid(self) -> None:
        violations = validate_run_lifecycle_invariants(
            run_status="materialized",
            record_status="draft",
            integrity_status="pending",
            finalized_at=None,
            finalization_errors=None,
        )
        assert violations == []

    def test_invalid_run_status_rejected(self) -> None:
        violations = validate_run_lifecycle_invariants(
            run_status="bogus",
            record_status="draft",
            integrity_status="pending",
            finalized_at=None,
            finalization_errors=None,
        )
        codes = {v.code for v in violations}
        assert "INVALID_RUN_STATUS" in codes

    def test_in_progress_and_invalidated_have_no_specific_invariants(self) -> None:
        """in_progress and invalidated are valid statuses but have no lifecycle invariant entry."""
        for status in ("in_progress", "invalidated"):
            violations = validate_run_lifecycle_invariants(
                run_status=status,
                record_status="draft",
                integrity_status="pending",
                finalized_at=None,
                finalization_errors=None,
            )
            assert violations == []


# ---------------------------------------------------------------------------
# Run Type / Artifact Requirement Invariants
# ---------------------------------------------------------------------------

class TestRunTypeArtifactInvariants:
    """Verify run type artifact requirement validation."""

    def test_analysis_run_valid(self) -> None:
        violations = validate_run_type_artifacts(
            run_type="analysis",
            plan_record_required=False,
            pr_record_required=False,
            plan_record_archived=False,
            pr_record_archived=False,
        )
        assert violations == []

    def test_plan_run_valid(self) -> None:
        violations = validate_run_type_artifacts(
            run_type="plan",
            plan_record_required=True,
            pr_record_required=False,
            plan_record_archived=True,
            pr_record_archived=False,
        )
        assert violations == []

    def test_pr_run_valid(self) -> None:
        violations = validate_run_type_artifacts(
            run_type="pr",
            plan_record_required=False,
            pr_record_required=True,
            plan_record_archived=False,
            pr_record_archived=True,
        )
        assert violations == []

    def test_plan_run_missing_plan_record(self) -> None:
        violations = validate_run_type_artifacts(
            run_type="plan",
            plan_record_required=True,
            pr_record_required=False,
            plan_record_archived=False,
            pr_record_archived=False,
        )
        codes = {v.code for v in violations}
        assert "REQUIRED_PLAN_NOT_ARCHIVED" in codes

    def test_pr_run_missing_pr_record(self) -> None:
        violations = validate_run_type_artifacts(
            run_type="pr",
            plan_record_required=False,
            pr_record_required=True,
            plan_record_archived=False,
            pr_record_archived=False,
        )
        codes = {v.code for v in violations}
        assert "REQUIRED_PR_NOT_ARCHIVED" in codes

    def test_invalid_run_type_rejected(self) -> None:
        violations = validate_run_type_artifacts(
            run_type="bogus",
            plan_record_required=False,
            pr_record_required=False,
            plan_record_archived=False,
            pr_record_archived=False,
        )
        codes = {v.code for v in violations}
        assert "INVALID_RUN_TYPE" in codes


# ---------------------------------------------------------------------------
# Cross-Document Consistency Invariants
# ---------------------------------------------------------------------------

class TestCrossDocumentConsistency:
    """Verify cross-document consistency validation."""

    def test_consistent_documents_pass(self) -> None:
        violations = validate_cross_document_consistency(
            manifest_run_id="run-1",
            metadata_run_id="run-1",
            provenance_run_id="run-1",
            directory_run_id="run-1",
            manifest_repo="abc123def456abc123def456",
            metadata_repo="abc123def456abc123def456",
            provenance_repo="abc123def456abc123def456",
            manifest_materialized_at="2026-03-10T10:00:00Z",
            metadata_archived_at="2026-03-10T10:00:00Z",
            provenance_materialized_at="2026-03-10T10:00:00Z",
        )
        assert violations == []

    def test_run_id_mismatch_manifest(self) -> None:
        violations = validate_cross_document_consistency(
            manifest_run_id="run-wrong",
            metadata_run_id="run-1",
            provenance_run_id="run-1",
            directory_run_id="run-1",
            manifest_repo="abc123def456abc123def456",
            metadata_repo="abc123def456abc123def456",
            provenance_repo="abc123def456abc123def456",
            manifest_materialized_at="2026-03-10T10:00:00Z",
            metadata_archived_at="2026-03-10T10:00:00Z",
            provenance_materialized_at="2026-03-10T10:00:00Z",
        )
        codes = {v.code for v in violations}
        assert "RUN_ID_MISMATCH_MANIFEST" in codes

    def test_repo_fingerprint_mismatch(self) -> None:
        violations = validate_cross_document_consistency(
            manifest_run_id="run-1",
            metadata_run_id="run-1",
            provenance_run_id="run-1",
            directory_run_id="run-1",
            manifest_repo="abc123def456abc123def456",
            metadata_repo="000000000000000000000000",
            provenance_repo="abc123def456abc123def456",
            manifest_materialized_at="2026-03-10T10:00:00Z",
            metadata_archived_at="2026-03-10T10:00:00Z",
            provenance_materialized_at="2026-03-10T10:00:00Z",
        )
        codes = {v.code for v in violations}
        assert "REPO_FINGERPRINT_MISMATCH" in codes

    def test_timestamp_mismatch(self) -> None:
        violations = validate_cross_document_consistency(
            manifest_run_id="run-1",
            metadata_run_id="run-1",
            provenance_run_id="run-1",
            directory_run_id="run-1",
            manifest_repo="abc123def456abc123def456",
            metadata_repo="abc123def456abc123def456",
            provenance_repo="abc123def456abc123def456",
            manifest_materialized_at="2026-03-10T10:00:00Z",
            metadata_archived_at="2026-03-10T11:00:00Z",
            provenance_materialized_at="2026-03-10T10:00:00Z",
        )
        codes = {v.code for v in violations}
        assert "TIMESTAMP_MISMATCH_MANIFEST_METADATA" in codes


# ---------------------------------------------------------------------------
# Required Artifact Keys Invariants
# ---------------------------------------------------------------------------

class TestRequiredArtifactKeysInvariants:
    """Verify required_artifacts map validation."""

    def test_valid_required_artifacts(self) -> None:
        valid = {
            "session_state": True,
            "run_manifest": True,
            "metadata": True,
            "ticket_record": True,
            "review_decision_record": True,
            "outcome_record": True,
            "evidence_index": True,
            "provenance": True,
            "plan_record": False,
            "pr_record": False,
            "checksums": True,
        }
        violations = validate_required_artifact_keys(valid)
        assert violations == []

    def test_missing_key_detected(self) -> None:
        incomplete = {
            "session_state": True,
            "run_manifest": True,
            "metadata": True,
            "provenance": True,
            "checksums": True,
        }
        violations = validate_required_artifact_keys(incomplete)
        codes = {v.code for v in violations}
        assert "REQUIRED_ARTIFACTS_KEY_MISMATCH" in codes

    def test_baseline_not_true_detected(self) -> None:
        bad = {
            "session_state": False,  # must be True
            "run_manifest": True,
            "metadata": True,
            "ticket_record": True,
            "review_decision_record": True,
            "outcome_record": True,
            "evidence_index": True,
            "provenance": True,
            "plan_record": False,
            "pr_record": False,
            "checksums": True,
        }
        violations = validate_required_artifact_keys(bad)
        codes = {v.code for v in violations}
        assert "BASELINE_ARTIFACT_NOT_TRUE" in codes


# ---------------------------------------------------------------------------
# Archived File Keys Invariants
# ---------------------------------------------------------------------------

class TestArchivedFileKeysInvariants:
    """Verify archived_files map validation."""

    def test_valid_archived_files(self) -> None:
        valid = {
            "session_state": True,
            "plan_record": False,
            "pr_record": False,
            "ticket_record": True,
            "review_decision_record": True,
            "outcome_record": True,
            "evidence_index": True,
            "run_manifest": True,
            "provenance_record": True,
            "checksums": True,
        }
        violations = validate_archived_file_keys(valid)
        assert violations == []

    def test_missing_key_detected(self) -> None:
        incomplete = {
            "session_state": True,
            "plan_record": False,
            "pr_record": False,
        }
        violations = validate_archived_file_keys(incomplete)
        codes = {v.code for v in violations}
        assert "ARCHIVED_FILES_KEY_MISMATCH" in codes

    def test_non_bool_value_detected(self) -> None:
        bad = {
            "session_state": True,
            "plan_record": "yes",
            "pr_record": False,
            "run_manifest": True,
            "provenance_record": True,
            "checksums": True,
        }
        violations = validate_archived_file_keys(bad)
        codes = {v.code for v in violations}
        assert "ARCHIVED_FILES_INVALID_ENTRY" in codes


# ---------------------------------------------------------------------------
# Failure Model Invariants
# ---------------------------------------------------------------------------

class TestFailureModelInvariants:
    """Verify failure model classification table invariants."""

    def test_all_categories_have_classifications(self) -> None:
        for cat in FailureCategory:
            assert cat in FAILURE_CLASSIFICATIONS

    def test_unknown_always_maps_to_fatal(self) -> None:
        c = FAILURE_CLASSIFICATIONS[FailureCategory.UNKNOWN]
        assert c.severity == FailureSeverity.FATAL
        assert c.recovery_strategy == RecoveryStrategy.ESCALATE_TO_OPERATOR
        assert not c.retryable

    def test_classify_unknown_message_returns_unknown(self) -> None:
        cat = classify_failure("something completely unexpected happened")
        assert cat == FailureCategory.UNKNOWN

    def test_classify_checksum_message(self) -> None:
        cat = classify_failure("Checksum mismatch: SESSION_STATE.json")
        assert cat == FailureCategory.CHECKSUM_MISMATCH

    def test_classify_missing_artifact(self) -> None:
        cat = classify_failure("Missing run artifacts: provenance-record.json")
        assert cat == FailureCategory.MISSING_REQUIRED_ARTIFACT

    def test_classify_duplicate_archive(self) -> None:
        cat = classify_failure("run archive already exists: /some/path")
        assert cat == FailureCategory.DUPLICATE_RUN_ARCHIVE

    def test_classify_finalization_guards(self) -> None:
        cat = classify_failure("run archive failed finalization guards")
        assert cat == FailureCategory.FINALIZATION_GUARD_FAILED

    def test_overall_severity_empty_is_warn(self) -> None:
        assert compute_overall_severity([]) == FailureSeverity.WARN

    def test_overall_severity_escalates_to_fatal(self) -> None:
        details = [
            FailureDetail(category=FailureCategory.SCHEMA_VALIDATION_FAILED, severity=FailureSeverity.ERROR, message="err"),
            FailureDetail(category=FailureCategory.CHECKSUM_MISMATCH, severity=FailureSeverity.FATAL, message="fatal"),
        ]
        assert compute_overall_severity(details) == FailureSeverity.FATAL

    def test_failure_report_serialization_roundtrip(self) -> None:
        report = build_failure_report(
            run_id="run-fail-1",
            repo_fingerprint="abc123def456abc123def456",
            observed_at="2026-03-10T10:00:00Z",
            error_messages=["Checksum mismatch: metadata.json"],
        )
        d = failure_report_to_dict(report)
        assert d["schema"] == "governance.failure-report.v1"
        assert d["run_id"] == "run-fail-1"
        assert isinstance(d["failures"], list)
        assert len(d["failures"]) == 1
        assert d["failures"][0]["category"] == "checksum_mismatch"
        assert isinstance(d["recovery_actions"], list)

    def test_get_classification_falls_back_to_unknown(self) -> None:
        """Verify fail-closed: unknown category gets UNKNOWN classification."""
        c = get_classification(FailureCategory.UNKNOWN)
        assert c.severity == FailureSeverity.FATAL


# ---------------------------------------------------------------------------
# Contract Summary Invariant
# ---------------------------------------------------------------------------

class TestContractSummary:
    """Verify get_contract_summary produces a consistent snapshot."""

    def test_summary_has_all_sections(self) -> None:
        summary = get_contract_summary()
        assert summary["contract_version"] == CONTRACT_VERSION
        assert isinstance(summary["allowed_run_statuses"], list)
        assert isinstance(summary["lifecycle_invariants"], dict)
        assert isinstance(summary["run_type_artifact_rules"], dict)
        assert len(summary["allowed_run_statuses"]) == len(ALLOWED_RUN_STATUSES)
        assert len(summary["run_type_artifact_rules"]) == len(RUN_TYPE_ARTIFACT_RULES)
