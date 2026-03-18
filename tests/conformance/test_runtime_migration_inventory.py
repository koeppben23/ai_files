"""
Runtime Migration Target Layout Test

Validates the planned target layout for governance_runtime/
This test is part of Wave 22a inventory - it validates the destination structure.
"""
from __future__ import annotations

import pytest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.conformance
class TestRuntimeMigrationTargetLayout:
    """Validate governance_runtime/ target layout for migration."""

    def test_governance_runtime_exists(self):
        """Target: governance_runtime/ directory."""
        assert (REPO_ROOT / "governance_runtime").is_dir()

    def test_target_application_subdir(self):
        """Target: governance_runtime/application/ exists as empty placeholder."""
        assert (REPO_ROOT / "governance_runtime" / "application").is_dir()

    def test_target_domain_subdir(self):
        """Target: governance_runtime/domain/ exists as empty placeholder."""
        assert (REPO_ROOT / "governance_runtime" / "domain").is_dir()

    def test_target_engine_subdir(self):
        """Target: governance_runtime/engine/ exists as empty placeholder."""
        assert (REPO_ROOT / "governance_runtime" / "engine").is_dir()

    def test_target_infrastructure_subdir(self):
        """Target: governance_runtime/infrastructure/ exists as empty placeholder."""
        assert (REPO_ROOT / "governance_runtime" / "infrastructure").is_dir()

    def test_target_kernel_subdir(self):
        """Target: governance_runtime/kernel/ exists as empty placeholder."""
        assert (REPO_ROOT / "governance_runtime" / "kernel").is_dir()

    def test_target_cli_subdir(self):
        """Target: governance_runtime/cli/ exists as empty placeholder."""
        assert (REPO_ROOT / "governance_runtime" / "cli").is_dir()

    def test_target_bin_subdir(self):
        """Target: governance_runtime/bin/ exists as empty placeholder."""
        assert (REPO_ROOT / "governance_runtime" / "bin").is_dir()

    def test_target_session_state_subdir(self):
        """Target: governance_runtime/session_state/ exists."""
        assert (REPO_ROOT / "governance_runtime" / "session_state").is_dir()

    def test_target_install_subdir(self):
        """Target: governance_runtime/install/ exists as empty placeholder."""
        assert (REPO_ROOT / "governance_runtime" / "install").is_dir()


@pytest.mark.conformance
class TestMigrationSourceInventory:
    """Inventory of source directories that need migration."""

    def test_source_governance_exists(self):
        """Source: governance/ directory (to be migrated)."""
        assert (REPO_ROOT / "governance").is_dir()

    def test_source_cli_exists(self):
        """Source: cli/ directory (to be migrated)."""
        assert (REPO_ROOT / "cli").is_dir()

    def test_source_bin_exists(self):
        """Source: bin/ directory (to be migrated)."""
        assert (REPO_ROOT / "bin").is_dir()

    def test_source_session_state_exists(self):
        """Source: session_state/ directory (to be migrated)."""
        assert (REPO_ROOT / "session_state").is_dir()

    def test_source_install_py_exists(self):
        """Source: install.py at root (to be migrated)."""
        assert (REPO_ROOT / "install.py").is_file()
