"""
Final Contract Alignment Conformance Test

Validates the final end-to-end state of the governance layer separation.
This is part of Wave 28a - final contract alignment.
"""
from __future__ import annotations

import pytest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.conformance
class TestFinalContractAlignment:
    """Validate final end-to-end state of governance layer separation."""

    def test_opencode_commands_has_9_rails(self):
        """Final: opencode/commands/ contains exactly 9 Rails."""
        commands_dir = REPO_ROOT / "opencode" / "commands"
        assert commands_dir.is_dir(), "opencode/commands/ must exist"
        
        md_files = list(commands_dir.glob("*.md"))
        assert len(md_files) == 9, f"Expected 9 Rails, found {len(md_files)}"

    def test_governance_content_reference_has_master_and_rules(self):
        """Final: governance_content/reference/ contains master.md and rules.md."""
        ref_dir = REPO_ROOT / "governance_content" / "reference"
        assert ref_dir.is_dir(), "governance_content/reference/ must exist"
        assert (ref_dir / "master.md").exists(), "master.md must exist at governance_content/reference/"
        assert (ref_dir / "rules.md").exists(), "rules.md must exist at governance_content/reference/"

    def test_governance_spec_has_phase_api_and_rules(self):
        """Final: governance_spec/ contains phase_api.yaml and rules.yml."""
        spec_dir = REPO_ROOT / "governance_spec"
        assert spec_dir.is_dir(), "governance_spec/ must exist"
        assert (spec_dir / "phase_api.yaml").exists(), "phase_api.yaml must exist"
        assert (spec_dir / "rules.yml").exists(), "rules.yml must exist"
        assert (spec_dir / "rulesets").is_dir(), "rulesets/ must exist"

    def test_governance_runtime_exists(self):
        """Final: governance_runtime/ exists as migration target."""
        gr_dir = REPO_ROOT / "governance_runtime"
        assert gr_dir.is_dir(), "governance_runtime/ must exist"
        
        # Should have key subdirectories
        assert (gr_dir / "kernel").is_dir(), "governance_runtime/kernel/ must exist"
        assert (gr_dir / "engine").is_dir(), "governance_runtime/engine/ must exist"
        assert (gr_dir / "infrastructure").is_dir(), "governance_runtime/infrastructure/ must exist"

    def test_governance_runtime_has_version(self):
        """Final: governance_runtime/VERSION exists as canonical version source."""
        version_file = REPO_ROOT / "governance_runtime" / "VERSION"
        assert version_file.exists(), "governance_runtime/VERSION must exist"

    def test_governance_runtime_has_install(self):
        """Final: governance_runtime/install/ contains installer."""
        install_dir = REPO_ROOT / "governance_runtime" / "install"
        assert install_dir.is_dir(), "governance_runtime/install/ must exist"
        assert (install_dir / "install.py").exists(), "governance_runtime/install/install.py must exist"

    def test_no_root_file_bridges(self):
        """Final: No Root Bridge files at root."""
        assert not (REPO_ROOT / "master.md").exists(), "master.md should not exist at root"
        assert not (REPO_ROOT / "rules.md").exists(), "rules.md should not exist at root"
        assert not (REPO_ROOT / "review.md").exists(), "review.md should not exist at root"
        assert not (REPO_ROOT / "phase_api.yaml").exists(), "phase_api.yaml should not exist at root"

    def test_no_root_directory_bridges(self):
        """Final: No Root Bridge directories at root."""
        assert not (REPO_ROOT / "docs").is_dir(), "docs/ should not exist at root"
        assert not (REPO_ROOT / "profiles").is_dir(), "profiles/ should not exist at root"
        assert not (REPO_ROOT / "rulesets").is_dir(), "rulesets/ should not exist at root"

    def test_governance_content_structure(self):
        """Final: governance_content/ has complete structure."""
        gc_dir = REPO_ROOT / "governance_content"
        assert gc_dir.is_dir(), "governance_content/ must exist"
        assert (gc_dir / "reference").is_dir(), "governance_content/reference/ must exist"
        assert (gc_dir / "docs").is_dir(), "governance_content/docs/ must exist"
        assert (gc_dir / "profiles").is_dir(), "governance_content/profiles/ must exist"
        assert (gc_dir / "templates").is_dir(), "governance_content/templates/ must exist"
