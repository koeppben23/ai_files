"""
OpenCode Command Surface Conformance Test

Validates that opencode/commands/ contains exactly 8 canonical Rails
and that master.md/rules.md remain at root as compatibility surface.
"""
from __future__ import annotations

import pytest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

CANONICAL_RAILS = frozenset({
    "continue.md",
    "plan.md",
    "review.md",
    "review-decision.md",
    "ticket.md",
    "implement.md",
    "implementation-decision.md",
    "audit-readout.md",
})


@pytest.mark.conformance
class TestOpenCodeCommandSurface:
    """Validate OpenCode command surface layout."""

    def test_opencode_commands_directory_exists(self):
        """Happy: opencode/commands/ directory exists."""
        commands_dir = REPO_ROOT / "opencode" / "commands"
        assert commands_dir.is_dir(), "opencode/commands/ must exist"

    def test_exactly_8_canonical_rails_in_opencode_commands(self):
        """Happy: opencode/commands/ contains exactly 8 canonical Rails."""
        commands_dir = REPO_ROOT / "opencode" / "commands"
        md_files = {f.name for f in commands_dir.glob("*.md")}
        assert len(md_files) == 8, f"Expected 8 Rails, found {len(md_files)}: {md_files}"
        assert md_files == CANONICAL_RAILS, f"Rail set mismatch. Expected {CANONICAL_RAILS}, got {md_files}"

    def test_master_md_not_in_opencode_commands(self):
        """Happy: master.md is NOT in opencode/commands/ (compatibility surface at root)."""
        commands_dir = REPO_ROOT / "opencode" / "commands"
        assert not (commands_dir / "master.md").exists(), \
            "master.md must NOT be in opencode/commands/ - it stays at root as compatibility surface"

    def test_rules_md_not_in_opencode_commands(self):
        """Happy: rules.md is NOT in opencode/commands/ (compatibility surface at root)."""
        commands_dir = REPO_ROOT / "opencode" / "commands"
        assert not (commands_dir / "rules.md").exists(), \
            "rules.md must NOT be in opencode/commands/ - it stays at root as compatibility surface"

    def test_root_rails_remain_for_backward_compatibility(self):
        """Edge: Root Rails remain as temporary compatibility surface."""
        root_rails = {f.name for f in REPO_ROOT.glob("*.md") if f.name in CANONICAL_RAILS}
        assert len(root_rails) > 0, f"Root Rails must remain for backward compatibility, found: {root_rails}"
