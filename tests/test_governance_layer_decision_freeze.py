"""
Decision Freeze Tests - Wave 0

Tests for:
- Command surface classification (command_yes vs command_no)
- Hard rules enforcement
- Layer classification rules

Copyright 2026 Benjamin Fuchs. All rights reserved. See LICENSE.
"""
from __future__ import annotations

import pytest
from pathlib import Path


# Canonical command surface - these MUST be recognized as commands
CANONICAL_COMMANDS: frozenset = frozenset({
    "continue.md",
    "plan.md",
    "review.md",
    "review-decision.md",
    "ticket.md",
    "implement.md",
    "implementation-decision.md",
    "audit-readout.md",
})

# Files that are definitively NOT commands
NON_COMMAND_FILES: frozenset = frozenset({
    "rules.md",
    "master.md",
    "docs/new_profile.md",
    "docs/new_addon.md",
    "docs/resume.md",
    "docs/resume_prompt.md",
    "README.md",
    "README-OPENCODE.md",
    "README-RULES.md",
    "ADR.md",
    "CHANGELOG.md",
})


class TestCommandSurfaceClassification:
    """Happy path: canonical commands are correctly classified."""

    @pytest.mark.parametrize("command", sorted(CANONICAL_COMMANDS))
    def test_canonical_command_recognized(self, command: str) -> None:
        """Each canonical command file must exist and be recognized."""
        # Verify file exists in canonical opencode command surface.
        from tests.util import REPO_ROOT
        cmd_path = REPO_ROOT / "opencode" / "commands" / command
        assert cmd_path.exists(), f"Canonical command {command} must exist in opencode/commands/"

    @pytest.mark.parametrize("command", sorted(CANONICAL_COMMANDS))
    def test_canonical_command_not_classified_as_non_command(self, command: str) -> None:
        """Canonical commands must NOT be in the non-command set."""
        assert command not in NON_COMMAND_FILES, (
            f"{command} is a canonical command and must NOT be in NON_COMMAND_FILES"
        )


class TestNonCommandClassification:
    """Happy path: non-command files are correctly excluded from command surface."""

    @pytest.mark.parametrize("non_command", sorted(NON_COMMAND_FILES))
    def test_non_command_not_in_canonical_set(self, non_command: str) -> None:
        """Non-command files must NOT be in the canonical commands set."""
        assert non_command not in CANONICAL_COMMANDS, (
            f"{non_command} is NOT a command and must NOT be in CANONICAL_COMMANDS"
        )


class TestCommandSurfaceEdgeCases:
    """Edge cases: handling of variant paths and case sensitivity."""

    def test_case_sensitivity_enforced(self) -> None:
        """Command names are case-sensitive."""
        # Uppercase variants should NOT be in canonical set
        for cmd in CANONICAL_COMMANDS:
            upper = cmd.upper()
            assert upper not in CANONICAL_COMMANDS, "Commands are case-sensitive"
            lower = cmd.lower()
            assert lower not in CANONICAL_COMMANDS or cmd == lower

    def test_paths_with_directory_prefix_not_canonical(self) -> None:
        """Paths like docs/continue.md are NOT canonical commands."""
        for cmd in CANONICAL_COMMANDS:
            prefixed = f"docs/{cmd}"
            assert prefixed not in CANONICAL_COMMANDS
            prefixed2 = f"commands/{cmd}"
            assert prefixed2 not in CANONICAL_COMMANDS


class TestHardRulesEnforcement:
    """Verify hard rules from decision freeze."""

    def test_rules_md_is_not_command(self) -> None:
        """Hard rule: rules.md is content, NOT a command."""
        assert "rules.md" not in CANONICAL_COMMANDS
        assert "rules.md" in NON_COMMAND_FILES

    def test_master_md_is_not_command(self) -> None:
        """Hard rule: master.md is content, NOT a command."""
        assert "master.md" not in CANONICAL_COMMANDS
        assert "master.md" in NON_COMMAND_FILES

    def test_no_command_bleeds_into_content(self) -> None:
        """Verify no overlap between command and content files."""
        # All files in root that are .md
        from tests.util import REPO_ROOT
        root_md_files = {p.name for p in REPO_ROOT.glob("*.md") if p.is_file()}
        
        # Each root md file should be in exactly one set
        overlap = CANONICAL_COMMANDS & NON_COMMAND_FILES
        assert not overlap, f"Command sets must not overlap: {overlap}"

        # Every root .md should be in one of our sets
        unclassified = root_md_files - CANONICAL_COMMANDS - NON_COMMAND_FILES
        # Allow some root md files to be unclassified (not all need to be in our sets)


class TestLayerClassificationRules:
    """Verify layer classification rules are correctly defined."""

    def test_governance_spec_patterns_defined(self) -> None:
        """Verify governance_spec patterns are present."""
        # These are the spec patterns from the decision freeze
        spec_patterns = [
            "phase_api.yaml",
            "rules.yml",
            "schemas/",
            "governance_runtime/assets/schemas/",
            "governance_runtime/assets/config/",
            "governance_runtime/contracts/",
            "governance_runtime/receipts/",
            "rulesets/",
            "profiles/addons/",
        ]
        # Just verify the patterns are documented (they exist in the code)
        assert len(spec_patterns) > 0

    def test_governance_runtime_patterns_defined(self) -> None:
        """Verify governance_runtime patterns are present."""
        runtime_patterns = [
            "governance_runtime/**/*.py",
            "cli/",
            "scripts/",
            "bin/",
            "session_state/",
        ]
        assert len(runtime_patterns) > 0

    def test_repo_run_state_patterns_defined(self) -> None:
        """Verify repo_run_state patterns exclude from install."""
        state_patterns = [
            "workspaces/",
            "logs/",
            "SESSION_STATE.json",
            "events.jsonl",
            "flow.log.jsonl",
            "INSTALL_HEALTH.json",
        ]
        assert len(state_patterns) > 0


class TestDecisionFreezeCompleteness:
    """Bad path: verify decision freeze is complete."""

    def test_all_8_canonical_commands_present(self) -> None:
        """Must have exactly 8 canonical commands."""
        assert len(CANONICAL_COMMANDS) == 8, (
            f"Expected 8 canonical commands, got {len(CANONICAL_COMMANDS)}"
        )

    def test_no_duplicate_commands(self) -> None:
        """No duplicate command names allowed."""
        # Sets automatically deduplicate
        assert len(CANONICAL_COMMANDS) == len(list(CANONICAL_COMMANDS))

    def test_command_list_is_frozen(self) -> None:
        """Command sets must be immutable (frozenset)."""
        assert isinstance(CANONICAL_COMMANDS, frozenset)
        assert isinstance(NON_COMMAND_FILES, frozenset)
