"""
Root Bridges Inventory and Conformance Test

Validates the inventory of Root Bridge files that should be deleted.
This is part of Wave 26a - root bridges inventory and conformance.
"""
from __future__ import annotations

import pytest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.conformance
class TestRootBridgesInventory:
    """Inventory of Root Bridge files."""

    def test_master_md_at_root_exists(self):
        """Inventory: master.md exists at root (should be moved to governance_content/reference/)."""
        root_master = REPO_ROOT / "master.md"
        # Document that this exists - will be deleted in 26b
        if root_master.exists():
            # This is a Root Bridge - should be migrated to governance_content/reference/
            gov_content_master = REPO_ROOT / "governance_content" / "reference" / "master.md"
            assert gov_content_master.exists(), \
                "master.md should exist at governance_content/reference/ before root version is deleted"

    def test_rules_md_at_root_exists(self):
        """Inventory: rules.md exists at root (should be moved to governance_content/reference/)."""
        root_rules = REPO_ROOT / "rules.md"
        if root_rules.exists():
            gov_content_rules = REPO_ROOT / "governance_content" / "reference" / "rules.md"
            assert gov_content_rules.exists(), \
                "rules.md should exist at governance_content/reference/ before root version is deleted"

    def test_review_md_at_root_exists(self):
        """Inventory: review.md exists at root (should be moved to governance_content/docs/)."""
        root_review = REPO_ROOT / "review.md"
        if root_review.exists():
            gov_content_review = REPO_ROOT / "governance_content" / "docs" / "review.md"
            assert gov_content_review.exists(), \
                "review.md should exist at governance_content/docs/ before root version is deleted"

    def test_phase_api_yaml_at_root_exists(self):
        """Inventory: phase_api.yaml exists at root (should be moved to governance_spec/)."""
        root_phase = REPO_ROOT / "phase_api.yaml"
        if root_phase.exists():
            gov_spec_phase = REPO_ROOT / "governance_spec" / "phase_api.yaml"
            assert gov_spec_phase.exists(), \
                "phase_api.yaml should exist at governance_spec/ before root version is deleted"

    def test_root_docs_directory_does_not_exist(self):
        """Inventory: docs/ at root should not exist (already migrated)."""
        root_docs = REPO_ROOT / "docs"
        # Should NOT exist at root
        assert not root_docs.is_dir(), "docs/ should not exist at root (migrated to governance_content/docs/)"

    def test_root_profiles_directory_does_not_exist(self):
        """Inventory: profiles/ at root should not exist (already migrated)."""
        root_profiles = REPO_ROOT / "profiles"
        # Should NOT exist at root
        assert not root_profiles.is_dir(), "profiles/ should not exist at root (migrated to governance_content/profiles/)"

    def test_root_rulesets_directory_does_not_exist(self):
        """Inventory: rulesets/ at root should not exist (already migrated)."""
        root_rulesets = REPO_ROOT / "rulesets"
        # Should NOT exist at root
        assert not root_rulesets.is_dir(), "rulesets/ should not exist at root (migrated to governance_spec/rulesets/)"


@pytest.mark.conformance
class TestRootBridgesDeletionTarget:
    """Validate SSOT locations for Root Bridge targets."""

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
