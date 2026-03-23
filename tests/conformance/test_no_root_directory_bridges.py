"""
Root Directory Bridges Confirmation Test

Confirms that Root Directory Bridges do not exist.
This is part of Wave 26c - confirm no root directory bridges.
"""
from __future__ import annotations

import pytest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.conformance
class TestNoRootDirectoryBridges:
    """Confirm Root Directory Bridges do not exist."""

    def test_no_docs_directory_at_root(self):
        """Confirm: docs/ does not exist at root."""
        assert not (REPO_ROOT / "docs").is_dir(), "docs/ should NOT exist at root"

    def test_no_profiles_directory_at_root(self):
        """Confirm: profiles/ does not exist at root."""
        assert not (REPO_ROOT / "profiles").is_dir(), "profiles/ should NOT exist at root"

    def test_no_rulesets_directory_at_root(self):
        """Confirm: rulesets/ does not exist at root."""
        assert not (REPO_ROOT / "rulesets").is_dir(), "rulesets/ should NOT exist at root"

    def test_governance_content_docs_exists(self):
        """Confirm: governance_content/docs/ exists."""
        assert (REPO_ROOT / "governance_content" / "docs").is_dir(), \
            "governance_content/docs/ should exist"

    def test_governance_content_profiles_exists(self):
        """Confirm: governance_content/profiles/ exists."""
        assert (REPO_ROOT / "governance_content" / "profiles").is_dir(), \
            "governance_content/profiles/ should exist"

    def test_governance_spec_rulesets_exists(self):
        """Confirm: governance_spec/rulesets/ exists."""
        assert (REPO_ROOT / "governance_spec" / "rulesets").is_dir(), \
            "governance_spec/rulesets/ should exist"
