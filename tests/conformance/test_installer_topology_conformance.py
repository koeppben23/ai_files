"""
Installer Topology Conformance Test

Validates that the installer recognizes the final repository topology.
This is part of Wave 24 - installer final topology.
"""
from __future__ import annotations

import pytest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.conformance
class TestInstallerTopologyConformance:
    """Validate installer final topology requirements."""

    def test_governance_runtime_package_exists(self):
        """Happy: governance_runtime/ package exists for installer mapping."""
        runtime_dir = REPO_ROOT / "governance_runtime"
        assert runtime_dir.is_dir(), "governance_runtime/ must exist for installer mapping"
        assert (runtime_dir / "application").is_dir(), "governance_runtime/application/ must exist"
        assert (runtime_dir / "domain").is_dir(), "governance_runtime/domain/ must exist"
        assert (runtime_dir / "engine").is_dir(), "governance_runtime/engine/ must exist"
        assert (runtime_dir / "infrastructure").is_dir(), "governance_runtime/infrastructure/ must exist"
        assert (runtime_dir / "kernel").is_dir(), "governance_runtime/kernel/ must exist"

    def test_governance_content_reference_exists(self):
        """Happy: governance_content/reference/ contains master.md and rules.md."""
        ref_dir = REPO_ROOT / "governance_content" / "reference"
        assert ref_dir.is_dir(), "governance_content/reference/ must exist"
        assert (ref_dir / "master.md").is_file(), "governance_content/reference/master.md must exist"
        assert (ref_dir / "rules.md").is_file(), "governance_content/reference/rules.md must exist"

    def test_governance_spec_structure_exists(self):
        """Happy: governance_spec/ contains phase_api.yaml and rulesets/."""
        spec_dir = REPO_ROOT / "governance_spec"
        assert spec_dir.is_dir(), "governance_spec/ must exist"
        assert (spec_dir / "phase_api.yaml").is_file(), "governance_spec/phase_api.yaml must exist"
        assert (spec_dir / "rules.yml").is_file(), "governance_spec/rules.yml must exist"
        assert (spec_dir / "rulesets").is_dir(), "governance_spec/rulesets/ must exist"

    def test_opencode_commands_surface_exists(self):
        """Happy: opencode/commands/ contains 8 canonical Rails."""
        commands_dir = REPO_ROOT / "opencode" / "commands"
        assert commands_dir.is_dir(), "opencode/commands/ must exist"
        md_files = list(commands_dir.glob("*.md"))
        assert len(md_files) == 8, f"Expected 8 Rails, found {len(md_files)}"

    def test_opencode_plugins_surface_not_present(self):
        """Happy: opencode/plugins/ pseudo-structure does not exist."""
        assert not (REPO_ROOT / "opencode" / "plugins").exists(), "opencode/plugins/ must not exist"

    def test_governance_content_structure_complete(self):
        """Happy: governance_content/ contains docs/, profiles/, templates/."""
        content_dir = REPO_ROOT / "governance_content"
        assert (content_dir / "docs").is_dir(), "governance_content/docs/ must exist"
        assert (content_dir / "profiles").is_dir(), "governance_content/profiles/ must exist"
        assert (content_dir / "templates").is_dir(), "governance_content/templates/ must exist"

    def test_no_master_rules_as_commands(self):
        """Happy: master.md and rules.md are NOT in opencode/commands/."""
        commands_dir = REPO_ROOT / "opencode" / "commands"
        assert not (commands_dir / "master.md").exists(), "master.md must NOT be in opencode/commands/"
        assert not (commands_dir / "rules.md").exists(), "rules.md must NOT be in opencode/commands/"
