"""
Version Source and Installer Entrypoint Conformance Test

Validates versioning and installer entrypoint requirements.
This is part of Wave 27a - versioning and installer entrypoint inventory.
"""
from __future__ import annotations

import pytest
from pathlib import Path
import re

REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.conformance
class TestVersionSourceConformance:
    """Validate version source requirements."""

    def test_governance_runtime_version_exists(self):
        """Target: governance_runtime/VERSION is the canonical source."""
        gr_version = REPO_ROOT / "governance_runtime" / "VERSION"
        assert gr_version.exists(), "governance_runtime/VERSION must exist as canonical source"

        # Must be valid SemVer (core with optional prerelease/build)
        content = gr_version.read_text(encoding="utf-8").strip()
        assert re.fullmatch(r"\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?", content), (
            "governance_runtime/VERSION must be SemVer-compatible"
        )

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
        """Root and canonical installer must stay functionally aligned on critical contracts."""
        root_install = REPO_ROOT / "install.py"
        canonical = REPO_ROOT / "governance_runtime" / "install" / "install.py"
        assert root_install.exists(), "install.py compatibility installer must exist"
        root_content = root_install.read_text(encoding="utf-8")
        canonical_content = canonical.read_text(encoding="utf-8")

        required_contract_tokens = [
            "GOVERNANCE_PATHS_SCHEMA",
            "def _write_python_binding_file(",
            "OPENCODE_JSON_NAME",
            "PYTHON_BINDING",
            "opencode-governance.paths.v1",
            "def _launcher_template_unix(",
            "def _launcher_template_windows(",
        ]
        for token in required_contract_tokens:
            assert token in root_content, f"Root install.py missing required contract token: {token}"
            assert token in canonical_content, f"Canonical installer missing required contract token: {token}"
