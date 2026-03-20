"""
Tests for Governance Layer Enforcement - Wave 8

Validates layer enforcement and boundary checking.

Copyright 2026 Benjamin Fuchs. All rights reserved. See LICENSE.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from governance_runtime.enforce import (
    ViolationType,
    LayerViolation,
    EnforcementResult,
    check_layer_assignment,
    check_state_file_location,
    check_packaging_rules,
    enforce_layers,
    get_layer_distribution,
    generate_layer_report,
)
from governance_runtime.layers import GovernanceLayer


class TestCheckLayerAssignment:
    """Test layer assignment checking."""

    def test_known_layer_returns_none(self) -> None:
        """Known layers return None (no violation)."""
        assert check_layer_assignment("commands/continue.md") is None
        assert check_layer_assignment("master.md") is None
        assert check_layer_assignment("phase_api.yaml") is None

    def test_unknown_layer_returns_violation(self) -> None:
        """Unknown layers return a violation."""
        result = check_layer_assignment("some/random/path.xyz")
        
        assert result is not None
        assert result.violation_type == ViolationType.UNKNOWN_FILE
        assert "Cannot determine layer" in result.message


class TestCheckStateFileLocation:
    """Test state file location checking."""

    def test_valid_log_location_returns_none(self) -> None:
        """Log in valid location returns no violation."""
        result = check_state_file_location("workspaces/abc123/logs/flow.log.jsonl")
        
        assert result is None

    def test_log_not_in_workspace_returns_violation(self) -> None:
        """Log not in workspace returns violation."""
        result = check_state_file_location("commands/logs/flow.log.jsonl")
        
        assert result is not None
        assert result.violation_type == ViolationType.LOG_NOT_IN_VALID_LOCATION


class TestCheckPackagingRules:
    """Test packaging rule checking."""

    def test_state_file_is_packaging_violation(self) -> None:
        """State files are packaging violations."""
        result = check_packaging_rules("SESSION_STATE.json")
        
        assert result is not None
        assert result.violation_type == ViolationType.PACKAGING_VIOLATION
        assert "should not be packaged" in result.message

    def test_content_is_not_packaging_violation(self) -> None:
        """Content files are not packaging violations."""
        result = check_packaging_rules("master.md")
        
        assert result is None

    def test_spec_is_not_packaging_violation(self) -> None:
        """Spec files are not packaging violations."""
        result = check_packaging_rules("phase_api.yaml")
        
        assert result is None


class TestEnforceLayers:
    """Test bulk layer enforcement."""

    def test_all_valid_passes(self) -> None:
        """All valid paths pass enforcement."""
        paths = [
            "commands/continue.md",
            "master.md",
            "phase_api.yaml",
            "governance/engine/orchestrator.py",
        ]
        
        result = enforce_layers(paths)
        
        assert result.passed is True
        assert len(result.violations) == 0
        assert result.total_files_checked == 4

    def test_violations_fail(self) -> None:
        """Paths with violations fail enforcement."""
        paths = [
            "commands/continue.md",
            "SESSION_STATE.json",  # packaging violation
        ]
        
        result = enforce_layers(paths, check_packaging=True)
        
        assert result.passed is False
        assert len(result.violations) == 1
        assert result.violations[0].violation_type == ViolationType.PACKAGING_VIOLATION

    def test_check_unknown_can_be_disabled(self) -> None:
        """Unknown layer check can be disabled."""
        paths = ["some/unknown/file.xyz"]
        
        result = enforce_layers(paths, check_unknown=True)
        assert result.passed is False
        
        result = enforce_layers(paths, check_unknown=False)
        assert result.passed is True


class TestGetLayerDistribution:
    """Test layer distribution calculation."""

    def test_counts_all_layers(self) -> None:
        """Correctly counts paths per layer."""
        paths = [
            "commands/continue.md",
            "commands/plan.md",
            "master.md",
            "rules.md",
            "phase_api.yaml",
            "governance/engine/orchestrator.py",
            "SESSION_STATE.json",
            "events.jsonl",
        ]
        
        dist = get_layer_distribution(paths)
        
        assert dist[GovernanceLayer.OPENCODE_INTEGRATION] == 2
        assert dist[GovernanceLayer.GOVERNANCE_CONTENT] == 2
        assert dist[GovernanceLayer.GOVERNANCE_SPEC] == 1
        assert dist[GovernanceLayer.GOVERNANCE_RUNTIME] == 1
        assert dist[GovernanceLayer.REPO_RUN_STATE] == 2


class TestGenerateLayerReport:
    """Test layer report generation."""

    def test_report_contains_layer_counts(self) -> None:
        """Report contains layer distribution."""
        paths = [
            "commands/continue.md",
            "master.md",
        ]
        
        report = generate_layer_report(paths)
        
        assert "Governance Layer Report" in report
        assert "OPENCODE_INTEGRATION:" in report
        assert "GOVERNANCE_CONTENT:" in report

    def test_report_contains_packaging_summary(self) -> None:
        """Report contains packaging summary."""
        paths = [
            "commands/continue.md",
            "master.md",
        ]
        
        report = generate_layer_report(paths, check_packaging=True)
        
        assert "Packaging Summary:" in report
        assert "Installable:" in report
        assert "Static payload:" in report


class TestLayerViolation:
    """Test LayerViolation dataclass."""

    def test_dataclass_fields(self) -> None:
        """LayerViolation has expected fields."""
        v = LayerViolation(
            path="test/path",
            violation_type=ViolationType.PACKAGING_VIOLATION,
            message="Test message",
            expected=GovernanceLayer.GOVERNANCE_CONTENT,
            actual=GovernanceLayer.REPO_RUN_STATE,
        )
        
        assert v.path == "test/path"
        assert v.violation_type == ViolationType.PACKAGING_VIOLATION
        assert v.message == "Test message"
        assert v.expected == GovernanceLayer.GOVERNANCE_CONTENT
        assert v.actual == GovernanceLayer.REPO_RUN_STATE
