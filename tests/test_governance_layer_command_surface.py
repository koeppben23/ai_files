"""
Command Surface Tests - Wave 4

Tests for:
- Canonical command identification
- Non-command file classification
- Command surface boundaries

Copyright 2026 Benjamin Fuchs. All rights reserved. See LICENSE.
"""
from __future__ import annotations

import pytest
from pathlib import Path

from governance.engine.command_surface import (
    CANONICAL_COMMANDS,
    NON_COMMAND_FILES,
    DEPRECATED_COMMANDS,
    is_canonical_command,
    is_non_command_file,
    is_command_surface_file,
    is_deprecated_command,
    get_all_command_surface_files,
)


class TestCanonicalCommands:
    """Test canonical command identification."""

    @pytest.mark.parametrize("cmd", sorted(CANONICAL_COMMANDS))
    def test_canonical_command_recognized(self, cmd: str) -> None:
        """Each canonical command must be recognized."""
        assert is_canonical_command(Path(cmd)) is True

    def test_all_8_canonical_commands_present(self) -> None:
        """Must have exactly 8 canonical commands."""
        assert len(CANONICAL_COMMANDS) == 8

    def test_canonical_commands_are_immutable(self) -> None:
        """Canonical commands must be immutable."""
        assert isinstance(CANONICAL_COMMANDS, frozenset)


class TestNonCommandFiles:
    """Test non-command file classification."""

    @pytest.mark.parametrize("file", sorted(NON_COMMAND_FILES))
    def test_non_command_file_recognized(self, file: str) -> None:
        """Each non-command file must be recognized."""
        assert is_non_command_file(Path(file)) is True

    def test_non_command_files_are_immutable(self) -> None:
        """Non-command files must be immutable."""
        assert isinstance(NON_COMMAND_FILES, frozenset)


class TestCommandSurfaceBoundary:
    """Test command surface boundaries."""

    def test_canonical_command_not_in_non_command(self) -> None:
        """Canonical commands must NOT be in non-command set."""
        overlap = CANONICAL_COMMANDS & NON_COMMAND_FILES
        assert not overlap, f"Overlap: {overlap}"

    def test_deprecated_not_in_canonical(self) -> None:
        """Deprecated commands must NOT be in canonical set."""
        overlap = DEPRECATED_COMMANDS & CANONICAL_COMMANDS
        assert not overlap, f"Deprecated in canonical: {overlap}"

    def test_command_surface_includes_both(self) -> None:
        """Command surface should include canonical + non-command."""
        surface = get_all_command_surface_files()
        # Should have 8 canonical + 4 non-command = 12
        assert len(surface) == 12


class TestDeprecatedCommands:
    """Test deprecated command identification."""

    @pytest.mark.parametrize("cmd", sorted(DEPRECATED_COMMANDS))
    def test_deprecated_command_recognized(self, cmd: str) -> None:
        """Each deprecated command must be recognized."""
        assert is_deprecated_command(Path(cmd)) is True

    def test_deprecated_not_canonical(self) -> None:
        """Deprecated commands are NOT canonical."""
        for cmd in DEPRECATED_COMMANDS:
            assert is_canonical_command(Path(cmd)) is False


class TestContentNotCommand:
    """Test that content files are NOT commands."""

    def test_readme_not_command(self) -> None:
        """README.md is NOT a command."""
        assert is_canonical_command(Path("README.md")) is False

    def test_adr_not_command(self) -> None:
        """ADR.md is NOT a command."""
        assert is_canonical_command(Path("ADR.md")) is False

    def test_changelog_not_command(self) -> None:
        """CHANGELOG.md is NOT a command."""
        assert is_canonical_command(Path("CHANGELOG.md")) is False


class TestCommandSurfaceCompleteness:
    """Test command surface completeness."""

    def test_continue_is_canonical(self) -> None:
        """continue.md must be canonical."""
        assert is_canonical_command(Path("continue.md")) is True

    def test_plan_is_canonical(self) -> None:
        """plan.md must be canonical."""
        assert is_canonical_command(Path("plan.md")) is True

    def test_review_is_canonical(self) -> None:
        """review.md must be canonical."""
        assert is_canonical_command(Path("review.md")) is True

    def test_review_decision_is_canonical(self) -> None:
        """review-decision.md must be canonical."""
        assert is_canonical_command(Path("review-decision.md")) is True

    def test_ticket_is_canonical(self) -> None:
        """ticket.md must be canonical."""
        assert is_canonical_command(Path("ticket.md")) is True

    def test_implement_is_canonical(self) -> None:
        """implement.md must be canonical."""
        assert is_canonical_command(Path("implement.md")) is True

    def test_implementation_decision_is_canonical(self) -> None:
        """implementation-decision.md must be canonical."""
        assert is_canonical_command(Path("implementation-decision.md")) is True

    def test_audit_readout_is_canonical(self) -> None:
        """audit-readout.md must be canonical."""
        assert is_canonical_command(Path("audit-readout.md")) is True
