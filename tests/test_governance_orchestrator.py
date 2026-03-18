"""WI-15 — Tests for governance/infrastructure/governance_orchestrator.py

End-to-end integration tests covering:
  - run_governance_pipeline()     — full pipeline on finalized archives
  - governance_export()           — governance-gated export
  - validate_archive_contract()   — contract validation layer
  - build_governance_summary()    — JSON-serializable summary

Happy / Edge / Corner / Bad coverage.
All I/O tests use pytest tmp_path fixture. No external dependencies.
"""

from __future__ import annotations

import json
import hashlib
from pathlib import Path

import pytest

from governance_runtime.domain.access_control import (
    AccessDecision,
    Action,
    Role,
)
from governance_runtime.domain.classification import ClassificationLevel
from governance_runtime.domain.regulated_mode import (
    DEFAULT_CONFIG,
    RegulatedModeConfig,
    RegulatedModeState,
)
from governance_runtime.domain.retention import (
    DeletionDecision,
    LegalHold,
    LegalHoldStatus,
)
from governance_runtime.infrastructure.archive_export import (
    EXPORT_MANIFEST_SCHEMA,
    write_legal_hold_record,
)
from governance_runtime.infrastructure.governance_orchestrator import (
    GovernancePipelineResult,
    build_governance_summary,
    execute_failure_recovery,
    governance_export,
    run_governance_pipeline,
    validate_archive_contract,
)
from governance_runtime.infrastructure.recovery_executor import build_resume_token


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_FINGERPRINT = "abc123def456abc123def456"
_RUN_ID = "run-20260101T000000Z"
_OBSERVED_AT = "2026-01-01T12:00:00Z"

_ACTIVE_REGULATED_CONFIG = RegulatedModeConfig(
    state=RegulatedModeState.ACTIVE,
    customer_id="CUST-001",
    compliance_framework="datev",
    activated_at="2025-01-01T00:00:00Z",
    activated_by="compliance-officer",
    minimum_retention_days=3650,
)


def _create_finalized_archive(base: Path, run_id: str = _RUN_ID) -> Path:
    """Create a minimal valid finalized archive."""
    archive_path = base / run_id
    archive_path.mkdir(parents=True)

    manifest = {
        "schema": "governance.run-manifest.v1",
        "schema_version": "v1",
        "artifact_type": "run_manifest",
        "artifact_id": f"run-manifest::{run_id}",
        "repo_fingerprint": _FINGERPRINT,
        "repo_slug": _FINGERPRINT,
        "run_id": run_id,
        "session_id": run_id,
        "created_at": _OBSERVED_AT,
        "created_by_component": "tests",
        "content_hash": "sha256:" + "0" * 64,
        "classification": "internal",
        "run_type": "analysis",
        "materialized_at": _OBSERVED_AT,
        "source_phase": "6",
        "source_active_gate": "",
        "source_next": "",
        "run_status": "finalized",
        "record_status": "finalized",
        "finalized_at": _OBSERVED_AT,
        "finalized_by": "tests",
        "integrity_status": "passed",
        "required_artifacts": {
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
        },
    }
    (archive_path / "run-manifest.json").write_text(
        json.dumps(manifest), encoding="utf-8"
    )

    metadata = {
        "schema": "governance.work-run.snapshot.v2",
        "repo_fingerprint": _FINGERPRINT,
        "run_id": run_id,
        "archived_at": _OBSERVED_AT,
        "source_phase": "6",
        "source_active_gate": "",
        "source_next": "",
        "snapshot_digest": "abc123",
        "snapshot_digest_scope": "session_state",
        "archived_files": {
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
        },
        "finalization_reason": "tests",
        "archive_status": "finalized",
    }
    (archive_path / "metadata.json").write_text(
        json.dumps(metadata), encoding="utf-8"
    )

    provenance = {
        "schema": "governance.provenance-record.v1",
        "schema_version": "v1",
        "artifact_type": "provenance_record",
        "artifact_id": f"provenance::{run_id}",
        "repo_fingerprint": _FINGERPRINT,
        "repo_slug": _FINGERPRINT,
        "run_id": run_id,
        "session_id": run_id,
        "created_at": _OBSERVED_AT,
        "created_by_component": "tests",
        "content_hash": "sha256:" + "0" * 64,
        "classification": "internal",
        "integrity_status": "pending",
        "record_status": "finalized",
        "finalized_at": _OBSERVED_AT,
        "finalized_by": "tests",
        "trigger": "new_work_session_created",
        "policy_fingerprint": "",
        "binding": {"repo_fingerprint": _FINGERPRINT, "session_run_id": run_id},
        "launcher": "governance.entrypoints.new_work_session",
        "timestamps": {"materialized_at": _OBSERVED_AT},
    }
    (archive_path / "provenance-record.json").write_text(
        json.dumps(provenance), encoding="utf-8"
    )

    minimal_header = {
        "schema_version": "v1",
        "run_id": run_id,
        "session_id": run_id,
        "repo_slug": _FINGERPRINT,
        "repo_fingerprint": _FINGERPRINT,
        "created_at": _OBSERVED_AT,
        "created_by_component": "tests",
        "content_hash": "sha256:" + "0" * 64,
        "classification": "internal",
        "integrity_status": "pending",
        "record_status": "finalized",
    }
    (archive_path / "ticket-record.json").write_text(
        json.dumps({"schema": "governance.ticket-record.v1", "artifact_type": "ticket_record", "artifact_id": f"ticket::{run_id}", **minimal_header}),
        encoding="utf-8",
    )
    (archive_path / "review-decision-record.json").write_text(
        json.dumps({"schema": "governance.review-decision-record.v1", "artifact_type": "review_decision_record", "artifact_id": f"review::{run_id}", **minimal_header}),
        encoding="utf-8",
    )
    (archive_path / "outcome-record.json").write_text(
        json.dumps({"schema": "governance.outcome-record.v1", "artifact_type": "outcome_record", "artifact_id": f"outcome::{run_id}", **minimal_header}),
        encoding="utf-8",
    )
    (archive_path / "evidence-index.json").write_text(
        json.dumps({"schema": "governance.evidence-index.v1", "artifact_type": "evidence_index", "artifact_id": f"evidence::{run_id}", **minimal_header}),
        encoding="utf-8",
    )

    (archive_path / "SESSION_STATE.json").write_text(
        json.dumps({"phase": 6}), encoding="utf-8"
    )
    checksum_files = {}
    for name in [
        "SESSION_STATE.json",
        "metadata.json",
        "run-manifest.json",
        "provenance-record.json",
        "ticket-record.json",
        "review-decision-record.json",
        "outcome-record.json",
        "evidence-index.json",
    ]:
        checksum_files[name] = "sha256:" + hashlib.sha256((archive_path / name).read_bytes()).hexdigest()
    (archive_path / "checksums.json").write_text(
        json.dumps({"schema": "governance.run-checksums.v1", "files": checksum_files}),
        encoding="utf-8",
    )

    return archive_path


# ===================================================================
# Happy path
# ===================================================================


class TestRunGovernancePipelineHappy:
    """Happy: full pipeline on a valid finalized archive."""

    def test_pipeline_passes_on_valid_archive(self, tmp_path: Path):
        archive = _create_finalized_archive(tmp_path)
        result = run_governance_pipeline(
            archive_path=archive,
            repo_fingerprint=_FINGERPRINT,
            run_id=_RUN_ID,
            observed_at=_OBSERVED_AT,
        )

        assert result.governance_passed is True
        assert result.archive_valid is True
        assert result.contract_valid is True

    def test_pipeline_returns_frozen_result(self, tmp_path: Path):
        archive = _create_finalized_archive(tmp_path)
        result = run_governance_pipeline(
            archive_path=archive,
            repo_fingerprint=_FINGERPRINT,
            run_id=_RUN_ID,
            observed_at=_OBSERVED_AT,
        )

        with pytest.raises(AttributeError):
            result.governance_passed = False  # type: ignore[misc]

    def test_pipeline_no_failure_report_when_clean(self, tmp_path: Path):
        archive = _create_finalized_archive(tmp_path)
        result = run_governance_pipeline(
            archive_path=archive,
            repo_fingerprint=_FINGERPRINT,
            run_id=_RUN_ID,
            observed_at=_OBSERVED_AT,
        )

        assert result.failure_report is None

    def test_pipeline_has_classification_summary(self, tmp_path: Path):
        archive = _create_finalized_archive(tmp_path)
        result = run_governance_pipeline(
            archive_path=archive,
            repo_fingerprint=_FINGERPRINT,
            run_id=_RUN_ID,
            observed_at=_OBSERVED_AT,
        )

        assert "total_classified_fields" in result.classification_summary
        assert "fields_by_level" in result.classification_summary

    def test_pipeline_has_retention_policy(self, tmp_path: Path):
        archive = _create_finalized_archive(tmp_path)
        result = run_governance_pipeline(
            archive_path=archive,
            repo_fingerprint=_FINGERPRINT,
            run_id=_RUN_ID,
            observed_at=_OBSERVED_AT,
        )

        assert result.retention_policy is not None
        assert len(result.retention_policy.periods) == 4

    def test_pipeline_has_deletion_evaluation(self, tmp_path: Path):
        archive = _create_finalized_archive(tmp_path)
        result = run_governance_pipeline(
            archive_path=archive,
            repo_fingerprint=_FINGERPRINT,
            run_id=_RUN_ID,
            observed_at=_OBSERVED_AT,
            archived_at_days_ago=0,
        )

        assert result.deletion_evaluation is not None
        # Just archived → blocked by retention
        assert result.deletion_evaluation.decision == DeletionDecision.BLOCKED_RETENTION

    def test_pipeline_access_defaults_to_system_verify(self, tmp_path: Path):
        archive = _create_finalized_archive(tmp_path)
        result = run_governance_pipeline(
            archive_path=archive,
            repo_fingerprint=_FINGERPRINT,
            run_id=_RUN_ID,
            observed_at=_OBSERVED_AT,
        )

        assert result.access_evaluation.role == Role.SYSTEM
        assert result.access_evaluation.action == Action.VERIFY_ARCHIVE
        assert result.access_evaluation.decision == AccessDecision.ALLOW


class TestRunGovernancePipelineRegulatedHappy:
    """Happy: pipeline with regulated mode active."""

    def test_regulated_mode_detected(self, tmp_path: Path):
        archive = _create_finalized_archive(tmp_path)
        result = run_governance_pipeline(
            archive_path=archive,
            repo_fingerprint=_FINGERPRINT,
            run_id=_RUN_ID,
            observed_at=_OBSERVED_AT,
            regulated_mode_config=_ACTIVE_REGULATED_CONFIG,
        )

        assert result.regulated_mode.is_active is True

    def test_regulated_mode_blocks_deletion(self, tmp_path: Path):
        archive = _create_finalized_archive(tmp_path)
        result = run_governance_pipeline(
            archive_path=archive,
            repo_fingerprint=_FINGERPRINT,
            run_id=_RUN_ID,
            observed_at=_OBSERVED_AT,
            regulated_mode_config=_ACTIVE_REGULATED_CONFIG,
            archived_at_days_ago=0,
        )

        assert result.deletion_evaluation is not None
        assert result.deletion_evaluation.decision in (
            DeletionDecision.BLOCKED_RETENTION,
            DeletionDecision.BLOCKED_REGULATED_MODE,
        )


class TestValidateArchiveContractHappy:
    """Happy: contract validation on valid archive."""

    def test_no_violations_on_valid_archive(self, tmp_path: Path):
        archive = _create_finalized_archive(tmp_path)
        violations = validate_archive_contract(archive)
        assert violations == []


class TestGovernanceExportHappy:
    """Happy: governance-gated export."""

    def test_export_succeeds_for_operator(self, tmp_path: Path):
        archive = _create_finalized_archive(tmp_path)
        export_path = tmp_path / "export"

        result, manifest = governance_export(
            archive_path=archive,
            export_path=export_path,
            repo_fingerprint=_FINGERPRINT,
            run_id=_RUN_ID,
            exported_at=_OBSERVED_AT,
            exported_by="test-operator",
            role=Role.OPERATOR,
        )

        assert result.governance_passed is True
        assert manifest is not None
        assert manifest.schema == EXPORT_MANIFEST_SCHEMA

    def test_export_creates_bundle_directory(self, tmp_path: Path):
        archive = _create_finalized_archive(tmp_path)
        export_path = tmp_path / "export"

        governance_export(
            archive_path=archive,
            export_path=export_path,
            repo_fingerprint=_FINGERPRINT,
            run_id=_RUN_ID,
            exported_at=_OBSERVED_AT,
            exported_by="test-operator",
            role=Role.OPERATOR,
        )

        assert export_path.is_dir()

    def test_export_with_redaction(self, tmp_path: Path):
        archive = _create_finalized_archive(tmp_path)
        export_path = tmp_path / "export"

        result, manifest = governance_export(
            archive_path=archive,
            export_path=export_path,
            repo_fingerprint=_FINGERPRINT,
            run_id=_RUN_ID,
            exported_at=_OBSERVED_AT,
            exported_by="test-operator",
            role=Role.OPERATOR,
            apply_redaction=True,
            redaction_max_level=ClassificationLevel.PUBLIC,
        )

        assert manifest is not None
        assert manifest.redaction_applied is True


class TestBuildGovernanceSummaryHappy:
    """Happy: summary is JSON-serializable."""

    def test_summary_has_expected_keys(self, tmp_path: Path):
        archive = _create_finalized_archive(tmp_path)
        result = run_governance_pipeline(
            archive_path=archive,
            repo_fingerprint=_FINGERPRINT,
            run_id=_RUN_ID,
            observed_at=_OBSERVED_AT,
        )
        summary = build_governance_summary(result)

        assert summary["schema"] == "governance.governance-summary.v1"
        assert summary["run_id"] == _RUN_ID
        assert summary["governance_passed"] is True

    def test_summary_is_json_serializable(self, tmp_path: Path):
        archive = _create_finalized_archive(tmp_path)
        result = run_governance_pipeline(
            archive_path=archive,
            repo_fingerprint=_FINGERPRINT,
            run_id=_RUN_ID,
            observed_at=_OBSERVED_AT,
        )
        summary = build_governance_summary(result)

        # Must not raise
        json_str = json.dumps(summary)
        assert isinstance(json_str, str)

    def test_summary_includes_deletion_info(self, tmp_path: Path):
        archive = _create_finalized_archive(tmp_path)
        result = run_governance_pipeline(
            archive_path=archive,
            repo_fingerprint=_FINGERPRINT,
            run_id=_RUN_ID,
            observed_at=_OBSERVED_AT,
        )
        summary = build_governance_summary(result)

        assert "deletion_decision" in summary
        assert "deletion_reason" in summary


# ===================================================================
# Edge cases
# ===================================================================


class TestRunGovernancePipelineEdge:
    """Edge: boundary conditions for pipeline."""

    def test_pipeline_with_operator_role(self, tmp_path: Path):
        archive = _create_finalized_archive(tmp_path)
        result = run_governance_pipeline(
            archive_path=archive,
            repo_fingerprint=_FINGERPRINT,
            run_id=_RUN_ID,
            observed_at=_OBSERVED_AT,
            role=Role.OPERATOR,
            action=Action.READ_ARCHIVE,
        )

        assert result.access_evaluation.decision == AccessDecision.ALLOW

    def test_pipeline_with_readonly_read_action(self, tmp_path: Path):
        archive = _create_finalized_archive(tmp_path)
        result = run_governance_pipeline(
            archive_path=archive,
            repo_fingerprint=_FINGERPRINT,
            run_id=_RUN_ID,
            observed_at=_OBSERVED_AT,
            role=Role.READONLY,
            action=Action.READ_ARCHIVE,
        )

        assert result.access_evaluation.decision == AccessDecision.ALLOW
        assert result.governance_passed is True

    def test_pipeline_old_archive_allows_deletion(self, tmp_path: Path):
        archive = _create_finalized_archive(tmp_path)
        result = run_governance_pipeline(
            archive_path=archive,
            repo_fingerprint=_FINGERPRINT,
            run_id=_RUN_ID,
            observed_at=_OBSERVED_AT,
            classification_level="public",
            archived_at_days_ago=500,  # > 365 short retention
        )

        assert result.deletion_evaluation is not None
        assert result.deletion_evaluation.decision == DeletionDecision.ALLOWED

    def test_pipeline_with_legal_holds(self, tmp_path: Path):
        archive = _create_finalized_archive(tmp_path)
        hold = LegalHold(
            hold_id="HOLD-001",
            scope_type="repo",
            scope_value=_FINGERPRINT,
            reason="Investigation",
            status=LegalHoldStatus.ACTIVE,
            created_at="2026-01-01T00:00:00Z",
            created_by="officer",
        )
        result = run_governance_pipeline(
            archive_path=archive,
            repo_fingerprint=_FINGERPRINT,
            run_id=_RUN_ID,
            observed_at=_OBSERVED_AT,
            classification_level="public",
            archived_at_days_ago=500,
            legal_holds=[hold],
        )

        assert result.deletion_evaluation is not None
        assert result.deletion_evaluation.decision == DeletionDecision.BLOCKED_LEGAL_HOLD


class TestGovernanceExportEdge:
    """Edge: export boundary conditions."""

    def test_export_with_legal_holds_from_dir(self, tmp_path: Path):
        archive = _create_finalized_archive(tmp_path)
        export_path = tmp_path / "export"
        holds_dir = tmp_path / "holds"

        hold = LegalHold(
            hold_id="HOLD-001",
            scope_type="repo",
            scope_value=_FINGERPRINT,
            reason="Investigation",
            status=LegalHoldStatus.ACTIVE,
            created_at="2026-01-01T00:00:00Z",
            created_by="officer",
        )
        write_legal_hold_record(holds_dir=holds_dir, hold=hold)

        result, manifest = governance_export(
            archive_path=archive,
            export_path=export_path,
            repo_fingerprint=_FINGERPRINT,
            run_id=_RUN_ID,
            exported_at=_OBSERVED_AT,
            exported_by="test-operator",
            role=Role.OPERATOR,
            legal_holds_dir=holds_dir,
        )

        # Export should still succeed (holds don't block export)
        assert manifest is not None

    def test_export_returns_pipeline_result_even_when_blocked(self, tmp_path: Path):
        """When export is denied, we still get the pipeline result."""
        archive = _create_finalized_archive(tmp_path)
        export_path = tmp_path / "export"

        result, manifest = governance_export(
            archive_path=archive,
            export_path=export_path,
            repo_fingerprint=_FINGERPRINT,
            run_id=_RUN_ID,
            exported_at=_OBSERVED_AT,
            exported_by="test-readonly",
            role=Role.READONLY,
        )

        # READONLY cannot export → governance fails on access
        assert manifest is None
        assert result is not None

    def test_regulated_export_requires_independent_approver(self, tmp_path: Path):
        archive = _create_finalized_archive(tmp_path)
        export_path = tmp_path / "export"

        result, manifest = governance_export(
            archive_path=archive,
            export_path=export_path,
            repo_fingerprint=_FINGERPRINT,
            run_id=_RUN_ID,
            exported_at=_OBSERVED_AT,
            exported_by="test-operator",
            role=Role.OPERATOR,
            regulated_mode_config=_ACTIVE_REGULATED_CONFIG,
        )

        assert manifest is None
        assert result.governance_passed is False

    def test_regulated_export_allows_with_approver_role(self, tmp_path: Path):
        archive = _create_finalized_archive(tmp_path)
        export_path = tmp_path / "export"

        result, manifest = governance_export(
            archive_path=archive,
            export_path=export_path,
            repo_fingerprint=_FINGERPRINT,
            run_id=_RUN_ID,
            exported_at=_OBSERVED_AT,
            exported_by="test-operator",
            role=Role.OPERATOR,
            approver_role=Role.APPROVER,
            regulated_mode_config=_ACTIVE_REGULATED_CONFIG,
        )

        assert result.governance_passed is True
        assert manifest is not None


class TestValidateArchiveContractEdge:
    """Edge: contract validation boundary cases."""

    def test_missing_manifest_reports_unreadable(self, tmp_path: Path):
        archive = tmp_path / "archive"
        archive.mkdir()
        (archive / "metadata.json").write_text(json.dumps({}), encoding="utf-8")
        (archive / "provenance-record.json").write_text(
            json.dumps({}), encoding="utf-8"
        )

        violations = validate_archive_contract(archive)
        assert len(violations) >= 1
        codes = [v.code for v in violations]
        assert "MANIFEST_UNREADABLE" in codes

    def test_missing_metadata_reports_unreadable(self, tmp_path: Path):
        archive = tmp_path / "archive"
        archive.mkdir()
        (archive / "run-manifest.json").write_text(
            json.dumps({"schema": "governance.run-manifest.v1"}),
            encoding="utf-8",
        )

        violations = validate_archive_contract(archive)
        codes = [v.code for v in violations]
        assert "METADATA_UNREADABLE" in codes


# ===================================================================
# Corner cases
# ===================================================================


class TestGovernancePipelineCorner:
    """Corner: unusual pipeline scenarios."""

    def test_pipeline_result_has_all_fields(self, tmp_path: Path):
        archive = _create_finalized_archive(tmp_path)
        result = run_governance_pipeline(
            archive_path=archive,
            repo_fingerprint=_FINGERPRINT,
            run_id=_RUN_ID,
            observed_at=_OBSERVED_AT,
        )

        # Ensure all fields are populated (not None where not Optional)
        assert result.run_id == _RUN_ID
        assert result.repo_fingerprint == _FINGERPRINT
        assert result.observed_at == _OBSERVED_AT
        assert isinstance(result.archive_valid, bool)
        assert isinstance(result.archive_errors, tuple)
        assert isinstance(result.contract_violations, tuple)
        assert isinstance(result.contract_valid, bool)
        assert result.access_evaluation is not None
        assert result.regulated_mode is not None
        assert isinstance(result.classification_summary, dict)
        assert result.retention_policy is not None
        assert isinstance(result.governance_passed, bool)

    def test_pipeline_default_regulated_is_inactive(self, tmp_path: Path):
        archive = _create_finalized_archive(tmp_path)
        result = run_governance_pipeline(
            archive_path=archive,
            repo_fingerprint=_FINGERPRINT,
            run_id=_RUN_ID,
            observed_at=_OBSERVED_AT,
        )

        assert result.regulated_mode.is_active is False

    def test_summary_without_failure_report(self, tmp_path: Path):
        archive = _create_finalized_archive(tmp_path)
        result = run_governance_pipeline(
            archive_path=archive,
            repo_fingerprint=_FINGERPRINT,
            run_id=_RUN_ID,
            observed_at=_OBSERVED_AT,
        )
        summary = build_governance_summary(result)

        assert "failure_report" not in summary

    def test_summary_with_failure_report(self, tmp_path: Path):
        """When governance fails, summary includes failure report."""
        result = run_governance_pipeline(
            archive_path=tmp_path / "nonexistent",
            repo_fingerprint=_FINGERPRINT,
            run_id=_RUN_ID,
            observed_at=_OBSERVED_AT,
        )
        summary = build_governance_summary(result)

        assert result.governance_passed is False
        assert "failure_report" in summary
        assert "suggested_recovery_strategy" in summary
        assert str(summary.get("recovery_resume_token", "")).startswith(f"resume::{_RUN_ID}::")


class TestFailureRecoveryCorner:
    def test_execute_failure_recovery_without_failure_report(self, tmp_path: Path):
        archive = _create_finalized_archive(tmp_path)
        result = run_governance_pipeline(
            archive_path=archive,
            repo_fingerprint=_FINGERPRINT,
            run_id=_RUN_ID,
            observed_at=_OBSERVED_AT,
        )

        execution = execute_failure_recovery(
            result=result,
            observed_at=_OBSERVED_AT,
            resume_token="resume::unused::token",
        )
        assert execution.strategy.value == "no_recovery"
        assert execution.attempted is False
        assert execution.succeeded is False

    def test_execute_failure_recovery_fails_closed_for_invalid_token(self, tmp_path: Path):
        result = run_governance_pipeline(
            archive_path=tmp_path / "missing",
            repo_fingerprint=_FINGERPRINT,
            run_id=_RUN_ID,
            observed_at=_OBSERVED_AT,
        )

        execution = execute_failure_recovery(
            result=result,
            observed_at=_OBSERVED_AT,
            resume_token="resume::bad::token",
        )
        assert execution.attempted is False
        assert execution.succeeded is False
        assert execution.message == "invalid resume token"

    def test_execute_failure_recovery_runs_primary_strategy_hook(self, tmp_path: Path):
        result = run_governance_pipeline(
            archive_path=tmp_path / "missing",
            repo_fingerprint=_FINGERPRINT,
            run_id=_RUN_ID,
            observed_at=_OBSERVED_AT,
        )
        token = build_resume_token(
            run_id=_RUN_ID,
            repo_fingerprint=_FINGERPRINT,
            observed_at=_OBSERVED_AT,
        )

        called = {"retry": False, "rearchive": False, "escalate": False}

        def _retry() -> bool:
            called["retry"] = True
            return True

        def _rearchive() -> bool:
            called["rearchive"] = True
            return True

        def _escalate(_token: str) -> bool:
            called["escalate"] = True
            return True

        execution = execute_failure_recovery(
            result=result,
            observed_at=_OBSERVED_AT,
            resume_token=token,
            retry_by_overwrite=_retry,
            invalidate_and_rearchive=_rearchive,
            escalate_to_operator=_escalate,
        )
        assert any(called.values())
        assert execution.attempted is True
        assert execution.succeeded is True


class TestGovernanceExportCorner:
    """Corner: export roundtrip scenarios."""

    def test_export_roundtrip_content_integrity(self, tmp_path: Path):
        archive = _create_finalized_archive(tmp_path)
        export_path = tmp_path / "export"

        result, manifest = governance_export(
            archive_path=archive,
            export_path=export_path,
            repo_fingerprint=_FINGERPRINT,
            run_id=_RUN_ID,
            exported_at=_OBSERVED_AT,
            exported_by="test-operator",
            role=Role.OPERATOR,
        )

        # Verify the exported manifest.json is readable and correct
        export_manifest_file = export_path / "export-manifest.json"
        assert export_manifest_file.is_file()
        data = json.loads(export_manifest_file.read_text(encoding="utf-8"))
        assert data["repo_fingerprint"] == _FINGERPRINT
        assert data["run_id"] == _RUN_ID


# ===================================================================
# Bad path / failure cases
# ===================================================================


class TestRunGovernancePipelineBad:
    """Bad: pipeline handles invalid archives gracefully."""

    def test_nonexistent_archive_fails_governance(self, tmp_path: Path):
        result = run_governance_pipeline(
            archive_path=tmp_path / "nonexistent",
            repo_fingerprint=_FINGERPRINT,
            run_id=_RUN_ID,
            observed_at=_OBSERVED_AT,
        )

        assert result.governance_passed is False
        assert result.archive_valid is False
        assert len(result.archive_errors) > 0

    def test_nonexistent_archive_has_failure_report(self, tmp_path: Path):
        result = run_governance_pipeline(
            archive_path=tmp_path / "nonexistent",
            repo_fingerprint=_FINGERPRINT,
            run_id=_RUN_ID,
            observed_at=_OBSERVED_AT,
        )

        assert result.failure_report is not None

    def test_non_finalized_archive_fails_governance(self, tmp_path: Path):
        archive = _create_finalized_archive(tmp_path)
        # Overwrite status to "active"
        manifest = json.loads(
            (archive / "run-manifest.json").read_text(encoding="utf-8")
        )
        manifest["run_status"] = "active"
        manifest["record_status"] = "draft"
        manifest["finalized_at"] = None
        manifest["integrity_status"] = "pending"
        (archive / "run-manifest.json").write_text(
            json.dumps(manifest), encoding="utf-8"
        )

        result = run_governance_pipeline(
            archive_path=archive,
            repo_fingerprint=_FINGERPRINT,
            run_id=_RUN_ID,
            observed_at=_OBSERVED_AT,
        )

        assert result.governance_passed is False
        assert result.archive_valid is False

    def test_access_denied_fails_governance(self, tmp_path: Path):
        archive = _create_finalized_archive(tmp_path)
        result = run_governance_pipeline(
            archive_path=archive,
            repo_fingerprint=_FINGERPRINT,
            run_id=_RUN_ID,
            observed_at=_OBSERVED_AT,
            role=Role.READONLY,
            action=Action.PURGE_ARCHIVE,
        )

        assert result.governance_passed is False
        assert result.access_evaluation.decision == AccessDecision.DENY
        assert result.failure_report is not None

    def test_empty_archive_directory_fails(self, tmp_path: Path):
        empty = tmp_path / "empty"
        empty.mkdir()

        result = run_governance_pipeline(
            archive_path=empty,
            repo_fingerprint=_FINGERPRINT,
            run_id=_RUN_ID,
            observed_at=_OBSERVED_AT,
        )

        assert result.governance_passed is False
        assert result.archive_valid is False


class TestGovernanceExportBad:
    """Bad: export blocks when governance fails."""

    def test_export_blocked_for_readonly_role(self, tmp_path: Path):
        archive = _create_finalized_archive(tmp_path)
        export_path = tmp_path / "export"

        result, manifest = governance_export(
            archive_path=archive,
            export_path=export_path,
            repo_fingerprint=_FINGERPRINT,
            run_id=_RUN_ID,
            exported_at=_OBSERVED_AT,
            exported_by="test-readonly",
            role=Role.READONLY,
        )

        assert manifest is None
        assert not export_path.exists()

    def test_export_blocked_for_invalid_archive(self, tmp_path: Path):
        export_path = tmp_path / "export"

        result, manifest = governance_export(
            archive_path=tmp_path / "nonexistent",
            export_path=export_path,
            repo_fingerprint=_FINGERPRINT,
            run_id=_RUN_ID,
            exported_at=_OBSERVED_AT,
            exported_by="test-operator",
            role=Role.OPERATOR,
        )

        assert manifest is None
        assert result.governance_passed is False

    def test_export_blocked_for_non_finalized_archive(self, tmp_path: Path):
        archive = _create_finalized_archive(tmp_path)
        manifest_data = json.loads(
            (archive / "run-manifest.json").read_text(encoding="utf-8")
        )
        manifest_data["run_status"] = "failed"
        manifest_data["record_status"] = "invalidated"
        manifest_data["integrity_status"] = "failed"
        manifest_data["finalized_at"] = None
        (archive / "run-manifest.json").write_text(
            json.dumps(manifest_data), encoding="utf-8"
        )

        export_path = tmp_path / "export"
        result, manifest = governance_export(
            archive_path=archive,
            export_path=export_path,
            repo_fingerprint=_FINGERPRINT,
            run_id=_RUN_ID,
            exported_at=_OBSERVED_AT,
            exported_by="test-operator",
            role=Role.OPERATOR,
        )

        assert manifest is None


class TestValidateArchiveContractBad:
    """Bad: contract validation catches problems."""

    def test_malformed_manifest_json(self, tmp_path: Path):
        archive = tmp_path / "archive"
        archive.mkdir()
        (archive / "run-manifest.json").write_text(
            "not valid json {{{", encoding="utf-8"
        )
        violations = validate_archive_contract(archive)
        assert len(violations) >= 1

    def test_missing_all_documents(self, tmp_path: Path):
        archive = tmp_path / "archive"
        archive.mkdir()
        violations = validate_archive_contract(archive)
        assert len(violations) >= 1
        codes = [v.code for v in violations]
        assert "MANIFEST_UNREADABLE" in codes


# ===================================================================
# Contract invariants
# ===================================================================


class TestGovernanceOrchestratorInvariants:
    """Contract: structural invariants that must hold."""

    def test_pipeline_result_is_frozen(self, tmp_path: Path):
        archive = _create_finalized_archive(tmp_path)
        result = run_governance_pipeline(
            archive_path=archive,
            repo_fingerprint=_FINGERPRINT,
            run_id=_RUN_ID,
            observed_at=_OBSERVED_AT,
        )

        with pytest.raises(AttributeError):
            result.run_id = "changed"  # type: ignore[misc]

    def test_summary_schema_version(self, tmp_path: Path):
        archive = _create_finalized_archive(tmp_path)
        result = run_governance_pipeline(
            archive_path=archive,
            repo_fingerprint=_FINGERPRINT,
            run_id=_RUN_ID,
            observed_at=_OBSERVED_AT,
        )
        summary = build_governance_summary(result)

        assert summary["schema"].startswith("governance.")
        assert "v1" in summary["schema"]

    def test_governance_passed_implies_archive_valid_and_contract_valid(self, tmp_path: Path):
        """If governance_passed is True, both archive and contract must be valid."""
        archive = _create_finalized_archive(tmp_path)
        result = run_governance_pipeline(
            archive_path=archive,
            repo_fingerprint=_FINGERPRINT,
            run_id=_RUN_ID,
            observed_at=_OBSERVED_AT,
        )

        if result.governance_passed:
            assert result.archive_valid is True
            assert result.contract_valid is True
            assert result.access_evaluation.decision == AccessDecision.ALLOW

    def test_governance_failed_has_errors_or_denial(self, tmp_path: Path):
        """If governance_passed is False, there must be errors or access denial."""
        result = run_governance_pipeline(
            archive_path=tmp_path / "nonexistent",
            repo_fingerprint=_FINGERPRINT,
            run_id=_RUN_ID,
            observed_at=_OBSERVED_AT,
        )

        assert result.governance_passed is False
        has_archive_errors = len(result.archive_errors) > 0
        has_violations = len(result.contract_violations) > 0
        has_denial = result.access_evaluation.decision == AccessDecision.DENY
        assert has_archive_errors or has_violations or has_denial
