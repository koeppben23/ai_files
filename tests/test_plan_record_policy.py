"""Tests for plan-record persistence policy integration.

Covers phase-window enforcement, can_write() for ARTIFACT_PLAN_RECORD,
write_policy allowlist, and persistence_artifacts.yaml integration.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from governance.application.policies.persistence_policy import (
    ARTIFACT_PLAN_RECORD,
    PersistencePolicyInput,
    can_write,
)
from governance.persistence.write_policy import (
    _ALLOWED_CANONICAL_VARIABLES,
    evaluate_target_path,
)
from tests.util import REPO_ROOT


# ---------------------------------------------------------------------------
# Policy: can_write for ARTIFACT_PLAN_RECORD
# ---------------------------------------------------------------------------

@pytest.mark.governance
class TestPlanRecordPersistencePolicy:

    def test_allowed_in_phase_4(self) -> None:
        decision = can_write(
            PersistencePolicyInput(
                artifact_kind=ARTIFACT_PLAN_RECORD,
                phase="4",
                mode="user",
                gate_approved=False,
                business_rules_executed=False,
                explicit_confirmation="",
            )
        )
        assert decision.allowed is True
        assert decision.reason_code == "none"

    def test_allowed_in_phase_5(self) -> None:
        decision = can_write(
            PersistencePolicyInput(
                artifact_kind=ARTIFACT_PLAN_RECORD,
                phase="5",
                mode="user",
                gate_approved=False,
                business_rules_executed=False,
                explicit_confirmation="",
            )
        )
        assert decision.allowed is True

    def test_allowed_in_phase_5_variant(self) -> None:
        decision = can_write(
            PersistencePolicyInput(
                artifact_kind=ARTIFACT_PLAN_RECORD,
                phase="5-ImplementationQA",
                mode="user",
                gate_approved=False,
                business_rules_executed=False,
                explicit_confirmation="",
            )
        )
        assert decision.allowed is True

    def test_blocked_in_phase_2(self) -> None:
        decision = can_write(
            PersistencePolicyInput(
                artifact_kind=ARTIFACT_PLAN_RECORD,
                phase="2",
                mode="user",
                gate_approved=False,
                business_rules_executed=False,
                explicit_confirmation="",
            )
        )
        assert decision.allowed is False
        assert decision.reason_code == "PERSIST_PHASE_MISMATCH"

    def test_blocked_in_phase_6(self) -> None:
        decision = can_write(
            PersistencePolicyInput(
                artifact_kind=ARTIFACT_PLAN_RECORD,
                phase="6",
                mode="user",
                gate_approved=False,
                business_rules_executed=False,
                explicit_confirmation="",
            )
        )
        assert decision.allowed is False
        assert decision.reason_code == "PERSIST_PHASE_MISMATCH"

    def test_blocked_in_phase_1(self) -> None:
        decision = can_write(
            PersistencePolicyInput(
                artifact_kind=ARTIFACT_PLAN_RECORD,
                phase="1",
                mode="user",
                gate_approved=False,
                business_rules_executed=False,
                explicit_confirmation="",
            )
        )
        assert decision.allowed is False

    def test_allowed_in_pipeline_mode(self) -> None:
        """Plan record does NOT require confirmation like workspace memory."""
        decision = can_write(
            PersistencePolicyInput(
                artifact_kind=ARTIFACT_PLAN_RECORD,
                phase="4",
                mode="pipeline",
                gate_approved=False,
                business_rules_executed=False,
                explicit_confirmation="",
            )
        )
        assert decision.allowed is True

    def test_no_gate_approval_required(self) -> None:
        """Plan record does not require gate approval."""
        decision = can_write(
            PersistencePolicyInput(
                artifact_kind=ARTIFACT_PLAN_RECORD,
                phase="4",
                mode="user",
                gate_approved=False,
                business_rules_executed=False,
                explicit_confirmation="",
            )
        )
        assert decision.allowed is True


# ---------------------------------------------------------------------------
# Write policy: PLAN_RECORD_FILE in canonical variables
# ---------------------------------------------------------------------------

@pytest.mark.governance
class TestPlanRecordWritePolicy:

    def test_plan_record_file_in_allowed_variables(self) -> None:
        assert "PLAN_RECORD_FILE" in _ALLOWED_CANONICAL_VARIABLES

    def test_plan_record_variable_path_valid(self) -> None:
        result = evaluate_target_path("${PLAN_RECORD_FILE}")
        assert result.valid is True
        assert result.reason_code == "none"

    def test_plan_record_variable_with_suffix_valid(self) -> None:
        result = evaluate_target_path("${PLAN_RECORD_FILE}/sub")
        assert result.valid is True


# ---------------------------------------------------------------------------
# persistence_artifacts.yaml: plan_record block exists
# ---------------------------------------------------------------------------

@pytest.mark.governance
class TestPlanRecordArtifactConfig:

    def test_plan_record_in_artifacts_yaml(self) -> None:
        import yaml

        yaml_path = REPO_ROOT / "governance" / "assets" / "config" / "persistence_artifacts.yaml"
        content = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
        artifacts = content.get("artifacts", {})
        assert "plan_record" in artifacts

    def test_plan_record_phase_window(self) -> None:
        import yaml

        yaml_path = REPO_ROOT / "governance" / "assets" / "config" / "persistence_artifacts.yaml"
        content = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
        plan_record = content["artifacts"]["plan_record"]
        phase_window = plan_record.get("phase_window", {})
        write_allowed = phase_window.get("write_allowed", [])
        assert "phase_4" in write_allowed or 4 in write_allowed or "4" in write_allowed


# ---------------------------------------------------------------------------
# Workspace paths
# ---------------------------------------------------------------------------

@pytest.mark.governance
class TestPlanRecordWorkspacePaths:

    def test_plan_record_path(self) -> None:
        from governance.infrastructure.workspace_paths import plan_record_path

        result = plan_record_path(Path("/workspaces"), "a" * 24)
        assert result == Path("/workspaces") / ("a" * 24) / "plan-record.json"

    def test_plan_record_archive_dir(self) -> None:
        from governance.infrastructure.workspace_paths import plan_record_archive_dir

        result = plan_record_archive_dir(Path("/workspaces"), "a" * 24)
        assert result == Path("/workspaces") / ("a" * 24) / "plan-record-archive"

    def test_plan_record_in_all_phase_artifact_paths(self) -> None:
        from governance.infrastructure.workspace_paths import all_phase_artifact_paths

        paths = all_phase_artifact_paths(Path("/workspaces"), "a" * 24)
        assert "plan_record" in paths

    def test_plan_record_in_phase4_artifacts(self) -> None:
        from governance.infrastructure.workspace_paths import PHASE4_ARTIFACTS

        assert "plan-record.json" in PHASE4_ARTIFACTS
