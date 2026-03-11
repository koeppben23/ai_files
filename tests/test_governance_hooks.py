"""WI-22 — Tests for governance/infrastructure/governance_hooks.py

Tests covering post-archive governance hook, regulated mode detection,
and config validation hook.
Happy / Edge / Corner / Bad coverage.
All I/O tests use pytest tmp_path fixture. No external dependencies.
"""

from __future__ import annotations

import json
import hashlib
from pathlib import Path

import pytest

from governance.domain.access_control import Role
from governance.domain.regulated_mode import (
    DEFAULT_CONFIG,
    RegulatedModeConfig,
    RegulatedModeState,
)
from governance.domain.retention import LegalHold, LegalHoldStatus
from governance.infrastructure.governance_hooks import (
    GovernanceHookResult,
    detect_regulated_mode,
    run_post_archive_governance,
    validate_governance_configs_at_startup,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_FINGERPRINT = "abc123def456abc123def456"
_RUN_ID = "run-20260101T000000Z"
_OBSERVED_AT = "2026-01-01T12:00:00Z"


def _create_finalized_archive(base: Path, run_id: str = _RUN_ID) -> Path:
    """Create a minimal valid finalized archive for governance hook testing."""
    archive_path = base / "governance-records" / _FINGERPRINT / "runs" / run_id
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
    (archive_path / "run-manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

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
    (archive_path / "metadata.json").write_text(json.dumps(metadata), encoding="utf-8")

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
    (archive_path / "provenance-record.json").write_text(json.dumps(provenance), encoding="utf-8")

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

    (archive_path / "SESSION_STATE.json").write_text(json.dumps({"phase": 6}), encoding="utf-8")
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
        json.dumps({"schema": "governance.run-checksums.v1", "files": checksum_files}), encoding="utf-8"
    )

    return archive_path


# ===================================================================
# Happy path
# ===================================================================


class TestRunPostArchiveGovernanceHappy:
    """Happy: governance hook runs successfully on valid archive."""

    def test_hook_executes_on_valid_archive(self, tmp_path: Path):
        archive = _create_finalized_archive(tmp_path)
        workspace_root = tmp_path / _FINGERPRINT
        workspace_root.mkdir(parents=True, exist_ok=True)

        result = run_post_archive_governance(
            archive_path=archive,
            repo_fingerprint=_FINGERPRINT,
            run_id=_RUN_ID,
            observed_at=_OBSERVED_AT,
            workspace_root=workspace_root,
        )

        assert result.executed is True
        assert result.governance_passed is True
        assert result.summary_path is not None
        assert result.error == ""

    def test_hook_writes_governance_summary(self, tmp_path: Path):
        archive = _create_finalized_archive(tmp_path)
        workspace_root = tmp_path / _FINGERPRINT
        workspace_root.mkdir(parents=True, exist_ok=True)

        result = run_post_archive_governance(
            archive_path=archive,
            repo_fingerprint=_FINGERPRINT,
            run_id=_RUN_ID,
            observed_at=_OBSERVED_AT,
            workspace_root=workspace_root,
        )

        assert result.summary_path is not None
        assert result.summary_path.is_file()
        summary = json.loads(result.summary_path.read_text(encoding="utf-8"))
        assert summary["schema"] == "governance.governance-summary.v1"
        assert summary["governance_passed"] is True

    def test_hook_writes_event_to_jsonl(self, tmp_path: Path):
        archive = _create_finalized_archive(tmp_path)
        workspace_root = tmp_path / _FINGERPRINT
        workspace_root.mkdir(parents=True, exist_ok=True)
        events_path = tmp_path / "events.jsonl"

        result = run_post_archive_governance(
            archive_path=archive,
            repo_fingerprint=_FINGERPRINT,
            run_id=_RUN_ID,
            observed_at=_OBSERVED_AT,
            workspace_root=workspace_root,
            events_path=events_path,
        )

        assert result.executed is True
        assert events_path.is_file()
        lines = events_path.read_text(encoding="utf-8").strip().split("\n")
        event = json.loads(lines[-1])
        assert event["event"] == "governance_pipeline_completed"
        assert event["governance_passed"] is True

    def test_hook_result_is_frozen(self, tmp_path: Path):
        archive = _create_finalized_archive(tmp_path)
        workspace_root = tmp_path / _FINGERPRINT
        workspace_root.mkdir(parents=True, exist_ok=True)

        result = run_post_archive_governance(
            archive_path=archive,
            repo_fingerprint=_FINGERPRINT,
            run_id=_RUN_ID,
            observed_at=_OBSERVED_AT,
            workspace_root=workspace_root,
        )

        with pytest.raises(AttributeError):
            result.executed = False  # type: ignore[misc]


class TestDetectRegulatedModeHappy:
    """Happy: regulated mode detection from workspace files."""

    def test_detect_inactive_when_no_file(self, tmp_path: Path):
        config = detect_regulated_mode(tmp_path)
        assert config.state == RegulatedModeState.INACTIVE

    def test_detect_active_from_file(self, tmp_path: Path):
        mode_file = tmp_path / "governance-mode.json"
        mode_file.write_text(json.dumps({
            "state": "active",
            "customer_id": "CUST-001",
            "compliance_framework": "DATEV",
            "activated_at": "2025-01-01T00:00:00Z",
            "activated_by": "admin",
            "minimum_retention_days": 3650,
        }), encoding="utf-8")

        config = detect_regulated_mode(tmp_path)
        assert config.state == RegulatedModeState.ACTIVE
        assert config.customer_id == "CUST-001"
        assert config.compliance_framework == "DATEV"


class TestValidateGovernanceConfigsHappy:
    """Happy: startup config validation passes."""

    def test_all_configs_valid_at_startup(self):
        results = validate_governance_configs_at_startup()
        for name, errors in results.items():
            assert errors == [], f"{name}: {errors}"


# ===================================================================
# Edge cases
# ===================================================================


class TestRunPostArchiveGovernanceEdge:
    """Edge: governance hook with various configurations."""

    def test_hook_with_regulated_mode_config(self, tmp_path: Path):
        archive = _create_finalized_archive(tmp_path)
        workspace_root = tmp_path / _FINGERPRINT
        workspace_root.mkdir(parents=True, exist_ok=True)

        config = RegulatedModeConfig(
            state=RegulatedModeState.ACTIVE,
            customer_id="CUST-001",
            compliance_framework="DATEV",
            activated_at="2025-01-01T00:00:00Z",
            activated_by="admin",
            minimum_retention_days=3650,
        )

        result = run_post_archive_governance(
            archive_path=archive,
            repo_fingerprint=_FINGERPRINT,
            run_id=_RUN_ID,
            observed_at=_OBSERVED_AT,
            workspace_root=workspace_root,
            regulated_mode_config=config,
        )

        assert result.executed is True
        assert result.governance_passed is True

    def test_hook_without_events_path(self, tmp_path: Path):
        archive = _create_finalized_archive(tmp_path)
        workspace_root = tmp_path / _FINGERPRINT
        workspace_root.mkdir(parents=True, exist_ok=True)

        result = run_post_archive_governance(
            archive_path=archive,
            repo_fingerprint=_FINGERPRINT,
            run_id=_RUN_ID,
            observed_at=_OBSERVED_AT,
            workspace_root=workspace_root,
            events_path=None,
        )

        assert result.executed is True


# ===================================================================
# Corner cases
# ===================================================================


class TestDetectRegulatedModeCorner:
    """Corner: unusual but valid regulated mode files."""

    def test_detect_transitioning_state(self, tmp_path: Path):
        mode_file = tmp_path / "governance-mode.json"
        mode_file.write_text(json.dumps({"state": "transitioning"}), encoding="utf-8")
        config = detect_regulated_mode(tmp_path)
        assert config.state == RegulatedModeState.TRANSITIONING

    def test_detect_empty_json_object(self, tmp_path: Path):
        mode_file = tmp_path / "governance-mode.json"
        mode_file.write_text("{}", encoding="utf-8")
        config = detect_regulated_mode(tmp_path)
        assert config.state == RegulatedModeState.INACTIVE

    def test_detect_with_extra_fields(self, tmp_path: Path):
        mode_file = tmp_path / "governance-mode.json"
        mode_file.write_text(json.dumps({
            "state": "active",
            "customer_id": "X",
            "extra_field": "ignored",
        }), encoding="utf-8")
        config = detect_regulated_mode(tmp_path)
        assert config.state == RegulatedModeState.ACTIVE


# ===================================================================
# Bad path
# ===================================================================


class TestRunPostArchiveGovernanceBad:
    """Bad: governance hook handles invalid inputs gracefully."""

    def test_hook_on_nonexistent_archive(self, tmp_path: Path):
        result = run_post_archive_governance(
            archive_path=tmp_path / "nonexistent",
            repo_fingerprint=_FINGERPRINT,
            run_id=_RUN_ID,
            observed_at=_OBSERVED_AT,
            workspace_root=tmp_path,
        )

        # Hook executes but governance pipeline fails (archive invalid)
        assert result.executed is True
        assert result.governance_passed is False

    def test_hook_on_empty_archive(self, tmp_path: Path):
        archive = tmp_path / "empty-archive"
        archive.mkdir()

        result = run_post_archive_governance(
            archive_path=archive,
            repo_fingerprint=_FINGERPRINT,
            run_id=_RUN_ID,
            observed_at=_OBSERVED_AT,
            workspace_root=tmp_path,
        )

        # Should execute but governance should fail
        assert result.executed is True
        assert result.governance_passed is False

    def test_hook_logs_failure_event(self, tmp_path: Path):
        events_path = tmp_path / "events.jsonl"

        result = run_post_archive_governance(
            archive_path=tmp_path / "nonexistent",
            repo_fingerprint=_FINGERPRINT,
            run_id=_RUN_ID,
            observed_at=_OBSERVED_AT,
            workspace_root=tmp_path,
            events_path=events_path,
        )

        # Hook executes but governance_passed is False
        assert result.executed is True
        assert result.governance_passed is False
        assert events_path.is_file()
        lines = events_path.read_text(encoding="utf-8").strip().split("\n")
        event = json.loads(lines[-1])
        assert event["event"] == "governance_pipeline_completed"
        assert event["governance_passed"] is False


class TestDetectRegulatedModeBad:
    """Bad: invalid regulated mode files."""

    def test_detect_invalid_json(self, tmp_path: Path):
        mode_file = tmp_path / "governance-mode.json"
        mode_file.write_text("not json", encoding="utf-8")
        config = detect_regulated_mode(tmp_path)
        assert config.state == RegulatedModeState.INACTIVE

    def test_detect_array_root(self, tmp_path: Path):
        mode_file = tmp_path / "governance-mode.json"
        mode_file.write_text("[]", encoding="utf-8")
        config = detect_regulated_mode(tmp_path)
        assert config.state == RegulatedModeState.INACTIVE

    def test_detect_unknown_state(self, tmp_path: Path):
        mode_file = tmp_path / "governance-mode.json"
        mode_file.write_text(json.dumps({"state": "invalid_state"}), encoding="utf-8")
        config = detect_regulated_mode(tmp_path)
        assert config.state == RegulatedModeState.INACTIVE
