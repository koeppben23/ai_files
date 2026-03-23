"""
Final Doc Alignment Conformance Test

Validates that documentation is aligned with the final end state.
This is part of Wave 28b - final doc alignment.
"""
from __future__ import annotations

import pytest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.conformance
class TestFinalDocAlignment:
    """Validate final documentation alignment."""

    def test_governance_content_reference_docs_exist(self):
        """Final: governance_content/reference/ contains master.md and rules.md."""
        ref_dir = REPO_ROOT / "governance_content" / "reference"
        assert (ref_dir / "master.md").exists(), "master.md should be at governance_content/reference/"
        assert (ref_dir / "rules.md").exists(), "rules.md should be at governance_content/reference/"

    def test_governance_content_docs_structure(self):
        """Final: governance_content/docs/ contains relevant docs."""
        docs_dir = REPO_ROOT / "governance_content" / "docs"
        assert docs_dir.is_dir(), "governance_content/docs/ should exist"
        
        # Should contain key documentation
        md_files = list(docs_dir.glob("*.md"))
        assert len(md_files) > 0, "governance_content/docs/ should contain markdown files"

    def test_governance_content_profiles_structure(self):
        """Final: governance_content/profiles/ contains profiles."""
        profiles_dir = REPO_ROOT / "governance_content" / "profiles"
        assert profiles_dir.is_dir(), "governance_content/profiles/ should exist"
        
        # Should contain profile files
        md_files = list(profiles_dir.glob("*.md"))
        assert len(md_files) > 0, "governance_content/profiles/ should contain markdown files"

    def test_governance_spec_structure(self):
        """Final: governance_spec/ contains spec files."""
        spec_dir = REPO_ROOT / "governance_spec"
        assert spec_dir.is_dir(), "governance_spec/ should exist"
        assert (spec_dir / "phase_api.yaml").exists(), "phase_api.yaml should be at governance_spec/"
        assert (spec_dir / "rules.yml").exists(), "rules.yml should be at governance_spec/"

    def test_no_root_level_governance_files(self):
        """Final: No governance files at root level that should be in governance_*/."""
        # These should NOT exist at root
        assert not (REPO_ROOT / "master.md").exists(), "master.md should not be at root"
        assert not (REPO_ROOT / "rules.md").exists(), "rules.md should not be at root"
        assert not (REPO_ROOT / "phase_api.yaml").exists(), "phase_api.yaml should not be at root"

    def test_opencode_commands_documented(self):
        """Final: opencode/commands/ contains Rails."""
        commands_dir = REPO_ROOT / "opencode" / "commands"
        assert commands_dir.is_dir(), "opencode/commands/ should exist"
        
        md_files = list(commands_dir.glob("*.md"))
        assert len(md_files) == 8, f"Expected 8 Rails, found {len(md_files)}"
