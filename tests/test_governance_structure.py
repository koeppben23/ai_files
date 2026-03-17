"""
Tests for Governance Directory Structure - Wave 12

Validates directory structure definitions and utilities.

Copyright 2026 Benjamin Fuchs. All rights reserved. See LICENSE.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from governance.structure import (
    DirectoryType,
    StructureRule,
    STRUCTURE_RULES,
    get_directory_type,
    is_valid_structure,
    get_legacy_paths,
    validate_directory_structure,
    suggest_migrations,
    get_structure_summary,
)


class TestDirectoryType:
    """Test DirectoryType enum."""

    def test_has_expected_values(self) -> None:
        """Enum has expected values."""
        assert DirectoryType.COMMAND_SURFACE is not None
        assert DirectoryType.GOVERNANCE_RUNTIME is not None
        assert DirectoryType.WORKSPACES is not None


class TestStructureRules:
    """Test structure rules definition."""

    def test_has_command_surface(self) -> None:
        """Rules include command surface."""
        rules = [r for r in STRUCTURE_RULES if r.directory_type == DirectoryType.COMMAND_SURFACE]
        assert len(rules) == 1
        assert "commands/" in rules[0].expected_paths

    def test_has_governance_runtime(self) -> None:
        """Rules include governance runtime."""
        rules = [r for r in STRUCTURE_RULES if r.directory_type == DirectoryType.GOVERNANCE_RUNTIME]
        assert len(rules) == 1
        assert "governance/" in rules[0].expected_paths

    def test_has_workspaces(self) -> None:
        """Rules include workspaces."""
        rules = [r for r in STRUCTURE_RULES if r.directory_type == DirectoryType.WORKSPACES]
        assert len(rules) == 1


class TestGetDirectoryType:
    """Test directory type detection."""

    def test_commands_is_command_surface(self) -> None:
        """commands/ is command surface."""
        assert get_directory_type("commands/") == DirectoryType.COMMAND_SURFACE
        assert get_directory_type("commands/continue.md") == DirectoryType.COMMAND_SURFACE

    def test_governance_is_runtime(self) -> None:
        """governance/ is runtime."""
        assert get_directory_type("governance/") == DirectoryType.GOVERNANCE_RUNTIME
        assert get_directory_type("governance/engine/orchestrator.py") == DirectoryType.GOVERNANCE_RUNTIME

    def test_docs_is_customer_docs(self) -> None:
        """docs/ is customer docs."""
        assert get_directory_type("docs/") == DirectoryType.CUSTOMER_DOCS
        assert get_directory_type("docs/readme.md") == DirectoryType.CUSTOMER_DOCS

    def test_schemas_is_specs(self) -> None:
        """schemas/ is governance specs."""
        assert get_directory_type("schemas/") == DirectoryType.GOVERNANCE_SPECS

    def test_governance_contracts_is_specs(self) -> None:
        """governance/contracts/ is governance specs."""
        assert get_directory_type("governance/contracts/") == DirectoryType.GOVERNANCE_SPECS

    def test_profiles_is_profiles(self) -> None:
        """profiles/ is profiles."""
        assert get_directory_type("profiles/") == DirectoryType.PROFILES

    def test_templates_is_templates(self) -> None:
        """templates/ is templates."""
        assert get_directory_type("templates/") == DirectoryType.TEMPLATES

    def test_workspaces_is_workspaces(self) -> None:
        """workspaces/ is workspaces."""
        assert get_directory_type("workspaces/") == DirectoryType.WORKSPACES
        assert get_directory_type("workspaces/abc123/") == DirectoryType.WORKSPACES

    def test_unknown_returns_none(self) -> None:
        """Unknown paths return None."""
        assert get_directory_type("unknown/") is None
        assert get_directory_type("random/file.txt") is None


class TestIsValidStructure:
    """Test structure validation."""

    def test_valid_path(self) -> None:
        """Valid paths return True."""
        is_valid, dir_type = is_valid_structure("commands/continue.md")
        assert is_valid is True
        assert dir_type == DirectoryType.COMMAND_SURFACE

    def test_invalid_path(self) -> None:
        """Invalid paths return False."""
        is_valid, dir_type = is_valid_structure("random/file.txt")
        assert is_valid is False
        assert dir_type is None


class TestGetLegacyPaths:
    """Test legacy paths."""

    def test_returns_tuple(self) -> None:
        """Returns tuple of legacy paths."""
        legacy = get_legacy_paths()
        assert isinstance(legacy, tuple)


class TestValidateDirectoryStructure:
    """Test directory structure validation."""

    def test_validates_existing(self, tmp_path: Path) -> None:
        """Validates existing directories."""
        (tmp_path / "commands").mkdir()
        (tmp_path / "governance").mkdir()
        
        result = validate_directory_structure(tmp_path)
        
        assert "valid_directories" in result
        assert "issues" in result


class TestGetStructureSummary:
    """Test structure summary."""

    def test_returns_counts(self, tmp_path: Path) -> None:
        """Returns file counts per directory."""
        (tmp_path / "commands").mkdir()
        (tmp_path / "commands" / "continue.md").write_text("# Continue")
        
        summary = get_structure_summary(tmp_path)
        
        assert "commands/" in summary
        assert summary["commands/"] >= 1
