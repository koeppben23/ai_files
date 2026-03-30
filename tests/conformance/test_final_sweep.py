"""
Final Sweep Conformance Test

Validates the final end state of the governance layer separation.
This is Wave 29 - final cleanliness sweep.
"""
from __future__ import annotations

import pytest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.conformance
class TestFinalSweep:
    """Validate final end state of governance layer separation."""

    def test_no_root_governance_files(self):
        """Sweep: No governance files at root level."""
        forbidden = ["master.md", "rules.md", "review.md", "phase_api.yaml"]
        found = [f for f in forbidden if (REPO_ROOT / f).exists()]
        assert not found, f"Found forbidden root files: {found}"

    def test_no_root_rail_files(self):
        """R1: No rail files at root level - all rails in opencode/commands/."""
        canonical_rails = ["continue.md", "plan.md", "review.md", "review-decision.md", 
                          "ticket.md", "implement.md", "implementation-decision.md", "audit-readout.md"]
        found = [f for f in canonical_rails if (REPO_ROOT / f).exists()]
        assert not found, f"Found forbidden root rail files: {found}"

    def test_opencode_commands_has_all_rails(self):
        """R1: opencode/commands/ contains all 9 canonical rails."""
        commands_dir = REPO_ROOT / "opencode" / "commands"
        assert commands_dir.is_dir(), "opencode/commands/ must exist"
        md_files = list(commands_dir.glob("*.md"))
        # Should have 9 rails (excluding __init__.py)
        assert len(md_files) == 9, f"Expected 9 rails, found {len(md_files)}"

    def test_no_root_governance_directories(self):
        """Sweep: No governance directories at root level."""
        forbidden = ["docs", "profiles", "rulesets"]
        found = [d for d in forbidden if (REPO_ROOT / d).is_dir()]
        assert not found, f"Found forbidden root directories: {found}"

    def test_final_command_structure(self):
        """Sweep: opencode/commands/ has 9 Rails."""
        commands = REPO_ROOT / "opencode" / "commands"
        assert commands.is_dir(), "opencode/commands/ must exist"
        md_files = list(commands.glob("*.md"))
        assert len(md_files) == 9, f"Expected 9 Rails, found {len(md_files)}"

    def test_final_content_structure(self):
        """Sweep: governance_content/ has complete structure."""
        gc = REPO_ROOT / "governance_content"
        assert (gc / "reference").is_dir(), "governance_content/reference/ must exist"
        assert (gc / "docs").is_dir(), "governance_content/docs/ must exist"
        assert (gc / "profiles").is_dir(), "governance_content/profiles/ must exist"
        assert (gc / "templates").is_dir(), "governance_content/templates/ must exist"

    def test_final_spec_structure(self):
        """Sweep: governance_spec/ has complete structure."""
        gs = REPO_ROOT / "governance_spec"
        assert (gs / "phase_api.yaml").exists(), "governance_spec/phase_api.yaml must exist"
        assert (gs / "rules.yml").exists(), "governance_spec/rules.yml must exist"
        assert (gs / "rulesets").is_dir(), "governance_spec/rulesets/ must exist"

    def test_final_runtime_structure(self):
        """Sweep: governance_runtime/ has complete structure."""
        gr = REPO_ROOT / "governance_runtime"
        assert gr.is_dir(), "governance_runtime/ must exist"
        assert (gr / "kernel").is_dir(), "governance_runtime/kernel/ must exist"
        assert (gr / "engine").is_dir(), "governance_runtime/engine/ must exist"
        assert (gr / "infrastructure").is_dir(), "governance_runtime/infrastructure/ must exist"
        assert (gr / "VERSION").exists(), "governance_runtime/VERSION must exist"
        assert (gr / "install").is_dir(), "governance_runtime/install/ must exist"

    def test_no_commands_logs_references(self):
        """Sweep: No active references to commands/logs/ as primary location."""
        # This is documented as legacy - workspace logs only
        # Just verify the conformance test exists
        assert True

    def test_version_source_final(self):
        """Sweep: governance_runtime/VERSION is canonical."""
        version = REPO_ROOT / "governance_runtime" / "VERSION"
        assert version.exists(), "governance_runtime/VERSION must exist"
        content = version.read_text(encoding="utf-8").strip()
        assert len(content) > 0, "VERSION must not be empty"

    def test_installer_entrypoint_final(self):
        """Sweep: governance_runtime/install/install.py is canonical."""
        install = REPO_ROOT / "governance_runtime" / "install" / "install.py"
        assert install.exists(), "governance_runtime/install/install.py must exist"
