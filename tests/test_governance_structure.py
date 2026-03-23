"""
Tests for Governance Directory Structure - Wave 12 (Revised)

Validates directory structure as thin wrapper over layer classification.

Copyright 2026 Benjamin Fuchs. All rights reserved. See LICENSE.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from governance_runtime.structure import (
    DirectoryType,
    get_directory_type,
    is_valid_structure,
    get_legacy_paths,
    get_layer_for_directory_type,
    get_allowed_directories_for_type,
    validate_structure_against_contract,
    get_structure_summary,
)
from governance_runtime import GovernanceLayer


class TestDirectoryType:
    """Test DirectoryType enum."""

    def test_has_expected_values(self) -> None:
        """Enum has expected values."""
        assert DirectoryType.COMMAND_SURFACE is not None
        assert DirectoryType.GOVERNANCE_RUNTIME is not None
        assert DirectoryType.WORKSPACES is not None


class TestGetDirectoryType:
    """Test directory type detection via layer classification."""

    def test_commands_is_command_surface(self) -> None:
        """commands/ maps to COMMAND_SURFACE via layer classification."""
        assert get_directory_type("commands/") == DirectoryType.COMMAND_SURFACE
        assert get_directory_type("commands/continue.md") == DirectoryType.COMMAND_SURFACE

    def test_governance_is_runtime(self) -> None:
        """governance/ maps to GOVERNANCE_RUNTIME via layer classification."""
        assert get_directory_type("governance_runtime/") == DirectoryType.GOVERNANCE_RUNTIME
        assert get_directory_type("governance_runtime/engine/orchestrator.py") == DirectoryType.GOVERNANCE_RUNTIME

    def test_docs_is_content(self) -> None:
        """docs/ maps to GOVERNANCE_CONTENT via layer classification."""
        assert get_directory_type("docs/") == DirectoryType.GOVERNANCE_CONTENT

    def test_schemas_is_specs(self) -> None:
        """schemas/ maps to GOVERNANCE_SPECS via layer classification."""
        assert get_directory_type("schemas/") == DirectoryType.GOVERNANCE_SPECS

    def test_profiles_is_content(self) -> None:
        """profiles/ maps to GOVERNANCE_CONTENT via layer classification."""
        assert get_directory_type("profiles/") == DirectoryType.GOVERNANCE_CONTENT

    def test_templates_is_content(self) -> None:
        """templates/ maps to GOVERNANCE_CONTENT via layer classification."""
        assert get_directory_type("templates/") == DirectoryType.GOVERNANCE_CONTENT

    def test_workspaces_is_workspaces(self) -> None:
        """workspaces/ maps to WORKSPACES via layer classification."""
        assert get_directory_type("workspaces/") == DirectoryType.WORKSPACES

    def test_unknown_returns_none(self) -> None:
        """Unknown paths return None."""
        assert get_directory_type("unknown/") is None
        assert get_directory_type("random/file.txt") is None


class TestIsValidStructure:
    """Test structure validation via layer classification."""

    def test_valid_path(self) -> None:
        """Valid paths return True via layer classification."""
        is_valid, dir_type = is_valid_structure("commands/continue.md")
        assert is_valid is True
        assert dir_type == DirectoryType.COMMAND_SURFACE

    def test_invalid_path(self) -> None:
        """Invalid paths return False via layer classification."""
        is_valid, dir_type = is_valid_structure("random/file.txt")
        assert is_valid is False
        assert dir_type is None


class TestGetLegacyPaths:
    """Test legacy paths."""

    def test_returns_tuple(self) -> None:
        """Returns tuple of legacy paths."""
        legacy = get_legacy_paths()
        assert isinstance(legacy, tuple)


class TestGetLayerForDirectoryType:
    """Test layer mapping."""

    def test_command_surface_maps_to_opencode_integration(self) -> None:
        """COMMAND_SURFACE maps to OPENCODE_INTEGRATION."""
        assert get_layer_for_directory_type(DirectoryType.COMMAND_SURFACE) == GovernanceLayer.OPENCODE_INTEGRATION

    def test_workspaces_maps_to_repo_run_state(self) -> None:
        """WORKSPACES maps to REPO_RUN_STATE."""
        assert get_layer_for_directory_type(DirectoryType.WORKSPACES) == GovernanceLayer.REPO_RUN_STATE


class TestValidateStructureAgainstContract:
    """Test contract-based validation."""

    def test_valid_structure(self) -> None:
        """Valid structure passes."""
        is_valid, msg = validate_structure_against_contract(
            "commands/continue.md",
            DirectoryType.COMMAND_SURFACE
        )
        assert is_valid is True

    def test_invalid_structure(self) -> None:
        """Invalid structure fails with proper message."""
        is_valid, msg = validate_structure_against_contract(
            "commands/master.md",  # This is CONTENT, not COMMAND
            DirectoryType.COMMAND_SURFACE
        )
        assert is_valid is False
        assert "GOVERNANCE_CONTENT" in msg


class TestGetStructureSummary:
    """Test structure summary."""

    def test_returns_counts(self, tmp_path: Path) -> None:
        """Returns file counts per directory type."""
        (tmp_path / "commands").mkdir()
        (tmp_path / "commands" / "continue.md").write_text("# Continue")
        
        summary = get_structure_summary(tmp_path)
        
        assert DirectoryType.COMMAND_SURFACE in summary
        assert summary[DirectoryType.COMMAND_SURFACE] >= 1
