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

    def test_governance_runtime_install_canonical(self):
        """Target: governance_runtime/install/install.py is the canonical entrypoint."""
        gr_install = REPO_ROOT / "governance_runtime" / "install" / "install.py"
        assert gr_install.exists(), "governance_runtime/install/install.py must exist as canonical entrypoint"

    def test_root_install_for_compatibility(self):
        """Legacy: Root install.py may exist for compatibility only."""
        root_install = REPO_ROOT / "install.py"
        
        # May exist but is not canonical anymore
        # Canonical source is governance_runtime/install/install.py
        pass
