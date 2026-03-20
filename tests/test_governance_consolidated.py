"""
Tests for Governance Consolidated API - Wave 9

Validates the complete governance public API from governance_runtime import.

Copyright 2026 Benjamin Fuchs. All rights reserved. See LICENSE.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from governance_runtime import (
    GovernanceLayer,
    classify_layer,
    get_layer_name,
    is_static_content_payload,
    is_installable_layer,
    is_state_file,
    is_log_file,
    is_command,
    is_spec_file,
    is_content_file,
    is_runtime_file,
    get_layer_for_path,
    iter_files_by_layer,
    validate_layer_assignment,
    get_layer_stats,
    ViolationType,
    LayerViolation,
    EnforcementResult,
    check_layer_assignment,
    check_state_file_location,
    check_packaging_rules,
    enforce_layers,
    generate_layer_report,
    get_layer_distribution,
)


class TestConsolidatedAPI:
    """Test that consolidated API is importable and functional."""

    def test_imports_work(self) -> None:
        """All expected imports are available."""
        assert GovernanceLayer is not None
        assert classify_layer is not None
        assert enforce_layers is not None
        assert generate_layer_report is not None

    def test_classify_layer_via_top_level_import(self) -> None:
        """classify_layer works via top-level import."""
        assert classify_layer("commands/continue.md") == GovernanceLayer.OPENCODE_INTEGRATION
        assert classify_layer("master.md") == GovernanceLayer.GOVERNANCE_CONTENT

    def test_enforce_via_top_level_import(self) -> None:
        """enforce_layers works via top-level import."""
        result = enforce_layers(["commands/continue.md", "master.md"])
        assert result.passed is True
        assert result.total_files_checked == 2


class TestLayerClassificationViaTopLevel:
    """Test layer classification via top-level import."""

    def test_commands_are_opencode_integration(self) -> None:
        """Canonical commands are opencode_integration."""
        assert classify_layer("commands/continue.md") == GovernanceLayer.OPENCODE_INTEGRATION
        assert classify_layer("commands/plan.md") == GovernanceLayer.OPENCODE_INTEGRATION

    def test_master_rules_are_content(self) -> None:
        """master.md and rules.md are content."""
        assert classify_layer("master.md") == GovernanceLayer.GOVERNANCE_CONTENT
        assert classify_layer("rules.md") == GovernanceLayer.GOVERNANCE_CONTENT

    def test_spec_is_spec_layer(self) -> None:
        """Spec files are governance_spec."""
        assert classify_layer("phase_api.yaml") == GovernanceLayer.GOVERNANCE_SPEC

    def test_python_is_runtime(self) -> None:
        """Python files are governance_runtime."""
        assert classify_layer("governance/engine/orchestrator.py") == GovernanceLayer.GOVERNANCE_RUNTIME

    def test_state_is_state_layer(self) -> None:
        """State files are repo_run_state."""
        assert classify_layer("SESSION_STATE.json") == GovernanceLayer.REPO_RUN_STATE


class TestEnforcementViaTopLevel:
    """Test enforcement via top-level import."""

    def test_valid_paths_pass(self) -> None:
        """Valid paths pass enforcement."""
        result = enforce_layers([
            "commands/continue.md",
            "master.md",
            "phase_api.yaml",
        ])
        assert result.passed is True

    def test_invalid_log_location_fails(self) -> None:
        """Log in invalid location fails."""
        result = enforce_layers(["commands/logs/flow.log.jsonl"], check_state_location=True)
        assert result.passed is False

    def test_packaging_violation_fails(self) -> None:
        """Packaging violation fails."""
        result = enforce_layers(["SESSION_STATE.json"], check_packaging=True)
        assert result.passed is False


class TestHelperFunctionsViaTopLevel:
    """Test helper functions via top-level import."""

    def test_get_layer_for_path(self) -> None:
        """get_layer_for_path returns complete info."""
        info = get_layer_for_path("commands/continue.md")
        
        assert info["layer"] == GovernanceLayer.OPENCODE_INTEGRATION
        assert info["name"] == "opencode_integration"
        assert info["is_installable"] is True

    def test_get_layer_stats(self) -> None:
        """get_layer_stats returns counts."""
        paths = [
            Path("commands/continue.md"),
            Path("master.md"),
            Path("phase_api.yaml"),
            Path("governance/engine/orchestrator.py"),
        ]
        
        stats = get_layer_stats(paths)
        
        assert stats["OPENCODE_INTEGRATION"] == 1
        assert stats["GOVERNANCE_CONTENT"] == 1
        assert stats["GOVERNANCE_SPEC"] == 1
        assert stats["GOVERNANCE_RUNTIME"] == 1

    def test_generate_report(self) -> None:
        """generate_layer_report works."""
        report = generate_layer_report([
            "commands/continue.md",
            "master.md",
        ])
        
        assert "Governance Layer Report" in report
        assert "OPENCODE_INTEGRATION:" in report


class TestPackagingFunctionsViaTopLevel:
    """Test packaging functions via top-level import."""

    def test_is_static_content_payload(self) -> None:
        """Correctly identifies static payload layers."""
        assert is_static_content_payload(GovernanceLayer.GOVERNANCE_CONTENT) is True
        assert is_static_content_payload(GovernanceLayer.GOVERNANCE_SPEC) is True
        assert is_static_content_payload(GovernanceLayer.REPO_RUN_STATE) is False

    def test_is_installable_layer(self) -> None:
        """Correctly identifies installable layers."""
        assert is_installable_layer(GovernanceLayer.GOVERNANCE_CONTENT) is True
        assert is_installable_layer(GovernanceLayer.GOVERNANCE_RUNTIME) is True
        assert is_installable_layer(GovernanceLayer.REPO_RUN_STATE) is False


class TestValidateLayerAssignmentViaTopLevel:
    """Test validate_layer_assignment via top-level import."""

    def test_valid_assignment_passes(self) -> None:
        """Valid assignment returns True."""
        assert validate_layer_assignment(
            "commands/continue.md",
            GovernanceLayer.OPENCODE_INTEGRATION
        ) is True

    def test_invalid_assignment_raises(self) -> None:
        """Invalid assignment raises LayerViolation."""
        with pytest.raises(LayerViolation):
            validate_layer_assignment(
                "master.md",
                GovernanceLayer.OPENCODE_INTEGRATION
            )
