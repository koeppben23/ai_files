"""
Tests for Governance Layers Integration - Wave 7

Validates the consolidated governance.layers API.

Copyright 2026 Benjamin Fuchs. All rights reserved. See LICENSE.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from governance.layers import (
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
    LayerViolation,
    get_layer_stats,
)


class TestClassifyLayer:
    """Test basic layer classification."""

    def test_command_is_opencode_integration(self) -> None:
        """Canonical commands are opencode_integration."""
        assert classify_layer("commands/continue.md") == GovernanceLayer.OPENCODE_INTEGRATION
        assert classify_layer("commands/plan.md") == GovernanceLayer.OPENCODE_INTEGRATION

    def test_master_rules_are_content(self) -> None:
        """master.md and rules.md are governance_content."""
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


class TestHelperFunctions:
    """Test helper functions."""

    def test_is_state_file(self) -> None:
        """is_state_file correctly identifies state files."""
        assert is_state_file("SESSION_STATE.json") is True
        assert is_state_file("events.jsonl") is True
        assert is_state_file("rules.md") is False

    def test_is_log_file(self) -> None:
        """is_log_file correctly identifies log files."""
        assert is_log_file("flow.log.jsonl") is True
        assert is_log_file("error.log.jsonl") is True
        assert is_log_file("rules.md") is False

    def test_is_command(self) -> None:
        """is_command correctly identifies canonical commands."""
        assert is_command("continue.md") is True
        assert is_command("plan.md") is True
        assert is_command("master.md") is False

    def test_is_spec_file(self) -> None:
        """is_spec_file correctly identifies spec files."""
        assert is_spec_file("phase_api.yaml") is True
        assert is_spec_file("rules.yml") is True

    def test_is_content_file(self) -> None:
        """is_content_file correctly identifies content files."""
        assert is_content_file("master.md") is True
        assert is_content_file("rules.md") is True

    def test_is_runtime_file(self) -> None:
        """is_runtime_file correctly identifies runtime files."""
        assert is_runtime_file("governance/engine/orchestrator.py") is True
        assert is_runtime_file("some/script.sh") is True


class TestGetLayerForPath:
    """Test get_layer_for_path function."""

    def test_returns_complete_info(self) -> None:
        """Returns complete layer information."""
        info = get_layer_for_path("commands/continue.md")
        
        assert info["layer"] == GovernanceLayer.OPENCODE_INTEGRATION
        assert info["name"] == "opencode_integration"
        assert info["is_installable"] is True
        assert info["is_static_payload"] is False

    def test_content_has_static_payload(self) -> None:
        """Content files have static_payload=True."""
        info = get_layer_for_path("master.md")
        
        assert info["layer"] == GovernanceLayer.GOVERNANCE_CONTENT
        assert info["is_static_payload"] is True
        assert info["is_installable"] is True


class TestValidateLayerAssignment:
    """Test layer validation."""

    def test_valid_assignment_passes(self) -> None:
        """Valid assignment returns True."""
        assert validate_layer_assignment(
            "commands/continue.md",
            GovernanceLayer.OPENCODE_INTEGRATION
        ) is True

    def test_invalid_assignment_raises_when_strict(self) -> None:
        """Invalid assignment raises LayerViolation when strict=True."""
        with pytest.raises(LayerViolation) as exc_info:
            validate_layer_assignment(
                "master.md",
                GovernanceLayer.OPENCODE_INTEGRATION,
                strict=True
            )
        
        assert exc_info.value.path == "master.md"
        assert exc_info.value.expected == GovernanceLayer.OPENCODE_INTEGRATION
        assert exc_info.value.actual == GovernanceLayer.GOVERNANCE_CONTENT

    def test_invalid_assignment_returns_false_when_not_strict(self) -> None:
        """Invalid assignment returns False when strict=False."""
        assert validate_layer_assignment(
            "master.md",
            GovernanceLayer.OPENCODE_INTEGRATION,
            strict=False
        ) is False


class TestIterFilesByLayer:
    """Test iter_files_by_layer function."""

    def test_filters_by_layer(self) -> None:
        """Filters paths by layer."""
        paths = [
            Path("commands/continue.md"),
            Path("master.md"),
            Path("phase_api.yaml"),
            Path("governance/engine/orchestrator.py"),
            Path("SESSION_STATE.json"),
        ]
        
        runtime_files = list(iter_files_by_layer(
            iter(paths),
            GovernanceLayer.GOVERNANCE_RUNTIME
        ))
        
        assert len(runtime_files) == 1
        assert runtime_files[0] == Path("governance/engine/orchestrator.py")


class TestGetLayerStats:
    """Test get_layer_stats function."""

    def test_counts_all_layers(self) -> None:
        """Correctly counts paths per layer."""
        paths = [
            Path("commands/continue.md"),
            Path("commands/plan.md"),
            Path("master.md"),
            Path("rules.md"),
            Path("phase_api.yaml"),
            Path("governance/engine/orchestrator.py"),
            Path("SESSION_STATE.json"),
            Path("events.jsonl"),
        ]
        
        stats = get_layer_stats(iter(paths))
        
        assert stats["OPENCODE_INTEGRATION"] == 2
        assert stats["GOVERNANCE_CONTENT"] == 2
        assert stats["GOVERNANCE_SPEC"] == 1
        assert stats["GOVERNANCE_RUNTIME"] == 1
        assert stats["REPO_RUN_STATE"] == 2


class TestPackagingFunctions:
    """Test packaging-related functions."""

    def test_is_static_content_payload(self) -> None:
        """Correctly identifies static content layers."""
        assert is_static_content_payload(GovernanceLayer.GOVERNANCE_CONTENT) is True
        assert is_static_content_payload(GovernanceLayer.GOVERNANCE_SPEC) is True
        assert is_static_content_payload(GovernanceLayer.GOVERNANCE_RUNTIME) is False
        assert is_static_content_payload(GovernanceLayer.OPENCODE_INTEGRATION) is False
        assert is_static_content_payload(GovernanceLayer.REPO_RUN_STATE) is False

    def test_is_installable_layer(self) -> None:
        """Correctly identifies installable layers."""
        assert is_installable_layer(GovernanceLayer.GOVERNANCE_CONTENT) is True
        assert is_installable_layer(GovernanceLayer.GOVERNANCE_SPEC) is True
        assert is_installable_layer(GovernanceLayer.GOVERNANCE_RUNTIME) is True
        assert is_installable_layer(GovernanceLayer.OPENCODE_INTEGRATION) is True
        assert is_installable_layer(GovernanceLayer.REPO_RUN_STATE) is False
        assert is_installable_layer(GovernanceLayer.UNKNOWN) is False
