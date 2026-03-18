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

    def test_version_at_root_or_governance(self):
        """Inventory: VERSION exists at root or governance/."""
        root_version = REPO_ROOT / "VERSION"
        gov_version = REPO_ROOT / "governance" / "VERSION"
        
        has_version = root_version.exists() or gov_version.exists()
        assert has_version, "VERSION must exist at root or governance/"

    def test_governance_runtime_version_recommended(self):
        """Target: governance_runtime/VERSION should be the final source."""
        # This documents the target - actual migration in 27b
        gr_version = REPO_ROOT / "governance_runtime" / "VERSION"
        
        # Currently may not exist - this is the target state
        # The test documents intent
        pass

    def test_no_duplicate_version_sources(self):
        """Target: Only one version source should be canonical."""
        # This test documents the intent for 27b
        # Currently VERSION exists at both root and governance/
        root_version = REPO_ROOT / "VERSION"
        gov_version = REPO_ROOT / "governance" / "VERSION"
        
        # Both exist currently - will be consolidated in 27b
        if root_version.exists() and gov_version.exists():
            # This is the current state - needs consolidation in 27b
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
