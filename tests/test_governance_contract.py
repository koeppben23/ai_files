"""
Tests for Governance Path Contract - Wave 10

Validates path contract validation module with real directory structure enforcement.

Copyright 2026 Benjamin Fuchs. All rights reserved. See LICENSE.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from governance.contract import (
    ContractRule,
    PathContractViolation,
    PathContractResult,
    validate_path_contract,
    validate_single_path,
    generate_contract_report,
    get_expected_directory_for_layer,
    get_allowed_prefixes_for_layer,
    check_directory_structure,
    validate_directory_structure,
)
from governance import GovernanceLayer


class TestCheckDirectoryStructure:
    """Test directory structure validation."""

    def test_command_in_commands_is_valid(self) -> None:
        """Command in commands/ is valid."""
        v = check_directory_structure("commands/continue.md")
        assert v is None

    def test_command_in_docs_is_invalid(self) -> None:
        """Command in docs/ is a structure violation."""
        v = check_directory_structure("docs/continue.md")
        
        assert v is not None
        assert v.rule == ContractRule.DIRECTORY_STRUCTURE

    def test_content_in_root_is_valid(self) -> None:
        """Content in root is valid."""
        v = check_directory_structure("master.md")
        assert v is None

    def test_content_in_commands_is_invalid(self) -> None:
        """Content in commands/ is a structure violation."""
        v = check_directory_structure("commands/master.md")
        
        assert v is not None
        assert v.rule == ContractRule.DIRECTORY_STRUCTURE

    def test_runtime_in_governance_is_valid(self) -> None:
        """Runtime in governance/ is valid."""
        v = check_directory_structure("governance/engine/orchestrator.py")
        assert v is None

    def test_runtime_in_commands_is_invalid(self) -> None:
        """Runtime in commands/ is a structure violation."""
        v = check_directory_structure("commands/script.py")
        
        assert v is not None
        assert v.rule == ContractRule.DIRECTORY_STRUCTURE

    def test_spec_in_root_is_valid(self) -> None:
        """Spec in root is valid."""
        v = check_directory_structure("phase_api.yaml")
        assert v is None

    def test_spec_in_governance_is_valid(self) -> None:
        """Spec in governance/contracts/ is valid."""
        v = check_directory_structure("governance/contracts/test.yaml")
        assert v is None

    def test_governance_yaml_in_commands_is_invalid(self) -> None:
        """Python file in commands/ is a structure violation."""
        v = check_directory_structure("commands/script.py")
        
        assert v is not None
        assert v.rule == ContractRule.DIRECTORY_STRUCTURE

    def test_multiple_violations(self) -> None:
        """Returns multiple violations correctly."""
        paths = [
            "commands/master.md",
            "docs/continue.md",
            "commands/script.py",
        ]
        
        violations = validate_directory_structure(paths)
        
        assert len(violations) == 3

    def test_valid_paths_return_empty(self) -> None:
        """Valid paths return no violations."""
        paths = [
            "commands/continue.md",
            "master.md",
            "governance/engine/orchestrator.py",
        ]
        
        violations = validate_directory_structure(paths)
        
        assert len(violations) == 0


class TestGetAllowedPrefixesForLayer:
    """Test machine-readable prefix lookup."""

    def test_returns_prefixes(self) -> None:
        """Returns expected prefixes."""
        prefixes = get_allowed_prefixes_for_layer(GovernanceLayer.OPENCODE_INTEGRATION)
        
        assert "commands/" in prefixes
        assert "plugins/" in prefixes

    def test_runtime_prefix(self) -> None:
        """Runtime has governance/ prefix."""
        prefixes = get_allowed_prefixes_for_layer(GovernanceLayer.GOVERNANCE_RUNTIME)
        
        assert "governance/" in prefixes


class TestValidateSinglePath:
    """Test single path validation with directory structure."""

    def test_valid_command_returns_empty(self) -> None:
        """Valid command returns no violations."""
        violations = validate_single_path("commands/continue.md")
        assert len(violations) == 0

    def test_invalid_log_location_returns_violation(self) -> None:
        """Log in invalid location returns violation."""
        violations = validate_single_path("commands/logs/flow.log.jsonl")
        
        assert any(v.rule == ContractRule.STATE_LOCATION for v in violations)

    def test_structure_violation_in_single(self) -> None:
        """Structure violation detected in single path validation."""
        violations = validate_single_path("docs/continue.md")
        
        assert any(v.rule == ContractRule.DIRECTORY_STRUCTURE for v in violations)

    def test_packaging_violation(self) -> None:
        """State file returns packaging violation."""
        violations = validate_single_path("SESSION_STATE.json", check_packaging=True)
        
        assert any(v.rule == ContractRule.PACKAGING for v in violations)


class TestPathContractResult:
    """Test PathContractResult dataclass."""

    def test_dataclass_fields(self) -> None:
        """Result has expected fields."""
        result = PathContractResult(
            passed=True,
            violations=[],
            total_paths_checked=10,
            layer_distribution={GovernanceLayer.OPENCODE_INTEGRATION: 5},
        )
        
        assert result.passed is True
        assert len(result.violations) == 0
        assert result.total_paths_checked == 10
        assert result.layer_distribution[GovernanceLayer.OPENCODE_INTEGRATION] == 5


class TestPathContractViolation:
    """Test PathContractViolation dataclass."""

    def test_dataclass_fields(self) -> None:
        """Violation has expected fields."""
        v = PathContractViolation(
            path="test/path",
            rule=ContractRule.PACKAGING,
            message="Test message",
            severity="error",
        )
        
        assert v.path == "test/path"
        assert v.rule == ContractRule.PACKAGING
        assert v.message == "Test message"
        assert v.severity == "error"


class TestGetExpectedDirectoryForLayer:
    """Test expected directory lookup."""

    def test_returns_expected_directories(self) -> None:
        """Returns correct expected directories."""
        result = get_expected_directory_for_layer(GovernanceLayer.OPENCODE_INTEGRATION)
        assert "commands" in result
        
        result = get_expected_directory_for_layer(GovernanceLayer.REPO_RUN_STATE)
        assert "workspaces" in result


class TestValidatePathContract:
    """Test bulk path contract validation."""

    def test_empty_directory_passes(self) -> None:
        """Empty directory passes validation."""
        import tempfile
        
        with tempfile.TemporaryDirectory() as tmpdir:
            result = validate_path_contract(tmpdir)
            assert result.passed is True


class TestGenerateContractReport:
    """Test contract report generation."""

    def test_report_contains_header(self) -> None:
        """Report contains expected header."""
        import tempfile
        
        with tempfile.TemporaryDirectory() as tmpdir:
            Path(tmpdir, "test.md").write_text("test")
            
            report = generate_contract_report(tmpdir)
            
            assert "Governance Path Contract Report" in report
            assert "Layer Distribution:" in report

    def test_verbose_report_contains_violations(self) -> None:
        """Verbose report contains violation details."""
        import tempfile
        
        with tempfile.TemporaryDirectory() as tmpdir:
            Path(tmpdir, "logs").mkdir()
            Path(tmpdir, "logs", "flow.log.jsonl").write_text("test")
            
            report = generate_contract_report(tmpdir, verbose=True)
            
            assert "Violations:" in report


class TestContractRule:
    """Test ContractRule enum."""

    def test_has_expected_values(self) -> None:
        """Enum has expected values."""
        assert ContractRule.LAYER_ASSIGNMENT is not None
        assert ContractRule.STATE_LOCATION is not None
        assert ContractRule.PACKAGING is not None
        assert ContractRule.DIRECTORY_STRUCTURE is not None
