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
        """Legacy VERSION files, if present, must mirror canonical runtime VERSION."""
        root_version = REPO_ROOT / "VERSION"
        gov_version = REPO_ROOT / "governance" / "VERSION"
        canonical = (REPO_ROOT / "governance_runtime" / "VERSION").read_text(encoding="utf-8").strip()

        if root_version.exists():
            assert root_version.read_text(encoding="utf-8").strip() == canonical
        if gov_version.exists():
            assert gov_version.read_text(encoding="utf-8").strip() == canonical


@pytest.mark.conformance
class TestInstallerEntrypointConformance:
    """Validate installer entrypoint requirements."""

    def test_governance_runtime_install_canonical(self):
        """Target: governance_runtime/install/install.py is the canonical entrypoint."""
        gr_install = REPO_ROOT / "governance_runtime" / "install" / "install.py"
        assert gr_install.exists(), "governance_runtime/install/install.py must exist as canonical entrypoint"

    def test_root_install_for_compatibility(self):
        """Root installer, if present, is compatibility surface while runtime installer is canonical."""
        root_install = REPO_ROOT / "install.py"
        canonical = REPO_ROOT / "governance_runtime" / "install" / "install.py"
        if root_install.exists():
            root_content = root_install.read_text(encoding="utf-8")
            canonical_content = canonical.read_text(encoding="utf-8")
            assert "LLM Governance System - Installer" in root_content
            assert "LLM Governance System - Installer" in canonical_content
