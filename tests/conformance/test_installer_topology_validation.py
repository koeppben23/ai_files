"""
Installer Topology Validation Test

Validates that the installer can validate the repository topology.
This is part of Wave 24b - installer topology validation.
"""
from __future__ import annotations

import pytest
from pathlib import Path
import re

REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.conformance
class TestInstallerTopologyValidation:
    """Validate installer topology validation function."""

    def test_validate_repo_topology_function_exists(self):
        """Happy: _validate_repo_topology function exists in installer."""
        install_path = REPO_ROOT / "governance_runtime" / "install" / "install.py"
        assert install_path.exists(), "governance_runtime/install/install.py must exist"
        
        content = install_path.read_text(encoding="utf-8")
        assert "def _validate_repo_topology" in content, \
            "_validate_repo_topology function must exist in installer"

    def test_validate_repo_topology_checks_opencode_commands(self):
        """Happy: validates opencode/commands/ exists with 8 Rails."""
        install_path = REPO_ROOT / "governance_runtime" / "install" / "install.py"
        content = install_path.read_text(encoding="utf-8")
        
        assert "opencode_commands = source_dir / \"opencode\" / \"commands\"" in content, \
            "Installer must check opencode/commands/"
        assert "md_files = list(opencode_commands.glob" in content, \
            "Installer must check for Rails files"
        assert "8" in content and "Rails" in content, \
            "Installer must check for 8 Rails"

    def test_validate_repo_topology_checks_governance_content_reference(self):
        """Happy: validates governance_content/reference/ master.md and rules.md."""
        install_path = REPO_ROOT / "governance_runtime" / "install" / "install.py"
        content = install_path.read_text(encoding="utf-8")
        
        assert "gov_content_ref" in content or "governance_content" in content, \
            "Installer must check governance_content/"
        assert "master.md" in content, \
            "Installer must check master.md"
        assert "rules.md" in content, \
            "Installer must check rules.md"

    def test_validate_repo_topology_checks_governance_spec(self):
        """Happy: validates governance_spec/ contains phase_api.yaml, rules.yml, rulesets/."""
        install_path = REPO_ROOT / "governance_runtime" / "install" / "install.py"
        content = install_path.read_text(encoding="utf-8")
        
        assert "governance_spec" in content, \
            "Installer must check governance_spec/"
        assert "phase_api.yaml" in content, \
            "Installer must check phase_api.yaml"
        assert "rules.yml" in content, \
            "Installer must check rules.yml"
        assert "rulesets" in content, \
            "Installer must check rulesets/"

    def test_validate_repo_topology_checks_governance_runtime(self):
        """Happy: validates governance_runtime/ exists as migration target."""
        install_path = REPO_ROOT / "governance_runtime" / "install" / "install.py"
        content = install_path.read_text(encoding="utf-8")
        
        assert "governance_runtime" in content, \
            "Installer must check governance_runtime/"
