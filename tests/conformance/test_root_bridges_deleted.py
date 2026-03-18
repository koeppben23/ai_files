"""
Root Bridges Deletion Test

Validates that Root Bridge files have been deleted.
This is part of Wave 26b - delete root file bridges.
"""
from __future__ import annotations

import pytest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.conformance
class TestRootBridgesDeleted:
    """Validate Root Bridge files are deleted."""

    def test_master_md_at_root_deleted(self):
        """Wave 26b: master.md at root is deleted."""
        root_master = REPO_ROOT / "master.md"
        assert not root_master.exists(), "master.md should be deleted from root"

    def test_rules_md_at_root_deleted(self):
        """Wave 26b: rules.md at root is deleted."""
        root_rules = REPO_ROOT / "rules.md"
        assert not root_rules.exists(), "rules.md should be deleted from root"

    def test_review_md_at_root_deleted(self):
        """Wave 26b: review.md at root is deleted."""
        root_review = REPO_ROOT / "review.md"
        assert not root_review.exists(), "review.md should be deleted from root"

    def test_phase_api_yaml_at_root_deleted(self):
        """Wave 26b: phase_api.yaml at root is deleted."""
        root_phase = REPO_ROOT / "phase_api.yaml"
        assert not root_phase.exists(), "phase_api.yaml should be deleted from root"

    def test_root_docs_directory_does_not_exist(self):
        """Wave 26b: docs/ at root should not exist."""
        root_docs = REPO_ROOT / "docs"
        assert not root_docs.is_dir(), "docs/ should not exist at root"

    def test_root_profiles_directory_does_not_exist(self):
        """Wave 26b: profiles/ at root should not exist."""
        root_profiles = REPO_ROOT / "profiles"
        assert not root_profiles.is_dir(), "profiles/ should not exist at root"

    def test_root_rulesets_directory_does_not_exist(self):
        """Wave 26b: rulesets/ at root should not exist."""
        root_rulesets = REPO_ROOT / "rulesets"
        assert not root_rulesets.is_dir(), "rulesets/ should not exist at root"


@pytest.mark.conformance
class TestSSOTLocationsIntact:
    """Validate SSOT locations are intact."""

    def test_master_md_in_governance_content_reference(self):
        """Target: master.md should be at governance_content/reference/."""
        target = REPO_ROOT / "governance_content" / "reference" / "master.md"
        assert target.exists(), "master.md should exist at governance_content/reference/"

    def test_rules_md_in_governance_content_reference(self):
        """Target: rules.md should be at governance_content/reference/."""
        target = REPO_ROOT / "governance_content" / "reference" / "rules.md"
        assert target.exists(), "rules.md should exist at governance_content/reference/"

    def test_review_md_in_governance_content_docs(self):
        """Target: review.md should be at governance_content/docs/."""
        target = REPO_ROOT / "governance_content" / "docs" / "review.md"
        assert target.exists(), "review.md should exist at governance_content/docs/"

    def test_phase_api_yaml_in_governance_spec(self):
        """Target: phase_api.yaml should be at governance_spec/."""
        target = REPO_ROOT / "governance_spec" / "phase_api.yaml"
        assert target.exists(), "phase_api.yaml should exist at governance_spec/"
