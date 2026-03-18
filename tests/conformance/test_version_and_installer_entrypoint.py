"""
Version Source and Installer Entrypoint Conformance Test

Validates versioning and installer entrypoint requirements.
This is part of Wave 27a - versioning and installer entrypoint inventory.
"""
from __future__ import annotations

import pytest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.conformance
class TestVersionSourceConformance:
    """Validate version source requirements."""

    def test_governance_runtime_version_exists(self):
        """Target: governance_runtime/VERSION is the canonical source."""
        gr_version = REPO_ROOT / "governance_runtime" / "VERSION"
        assert gr_version.exists(), "governance_runtime/VERSION must exist as canonical source"
        
        # Should have valid semver content
        content = gr_version.read_text(encoding="utf-8").strip()
        assert len(content) > 0, "governance_runtime/VERSION must not be empty"

    def test_version_source_for_compatibility(self):
        """Legacy: VERSION at root or governance/ may exist for compatibility only."""
        root_version = REPO_ROOT / "VERSION"
        gov_version = REPO_ROOT / "governance" / "VERSION"
        
        # These may exist but are not canonical anymore
        # Canonical source is governance_runtime/VERSION
        pass


@pytest.mark.conformance
class TestInstallerEntrypointConformance:
    """Validate installer entrypoint requirements."""

    def test_install_py_exists(self):
        """Inventory: install.py exists at root or governance_runtime/install/."""
        root_install = REPO_ROOT / "install.py"
        gr_install = REPO_ROOT / "governance_runtime" / "install" / "install.py"
        
        has_install = root_install.exists() or gr_install.exists()
        assert has_install, "install.py must exist"

    def test_governance_runtime_install_target(self):
        """Target: install.py should eventually be at governance_runtime/install/install.py."""
        # This documents the target - actual migration in 27c
        gr_install = REPO_ROOT / "governance_runtime" / "install" / "install.py"
        
        # Currently exists at both locations
        pass
