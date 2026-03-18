"""
SSOT Path Enforcer Test

Validates that critical SSOT paths are enforced and legacy fallbacks are removed.
This is part of Wave 23a - removing high-confidence legacy fallbacks.
"""
from __future__ import annotations

import pytest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.conformance
class TestSSOTPathEnforcement:
    """Validate SSOT-only path enforcement."""

    def test_master_path_points_to_governance_content_reference(self):
        """Happy: master.md is at governance_content/reference/master.md."""
        from tests.util import get_master_path
        path = get_master_path()
        assert "governance_content/reference/master.md" in str(path), \
            f"master.md must be at governance_content/reference/, got: {path}"
        assert path.exists(), f"master.md must exist at: {path}"

    def test_rules_path_points_to_governance_content_reference(self):
        """Happy: rules.md is at governance_content/reference/rules.md."""
        from tests.util import get_rules_path
        path = get_rules_path()
        assert "governance_content/reference/rules.md" in str(path), \
            f"rules.md must be at governance_content/reference/, got: {path}"
        assert path.exists(), f"rules.md must exist at: {path}"

    def test_phase_api_path_points_to_governance_spec(self):
        """Happy: phase_api.yaml is at governance_spec/phase_api.yaml."""
        from tests.util import get_phase_api_path
        path = get_phase_api_path()
        assert "governance_spec/phase_api.yaml" in str(path), \
            f"phase_api.yaml must be at governance_spec/, got: {path}"
        assert path.exists(), f"phase_api.yaml must exist at: {path}"

    def test_docs_path_points_to_governance_content_docs(self):
        """Happy: docs are at governance_content/docs/."""
        from tests.util import get_docs_path
        path = get_docs_path()
        assert "governance_content/docs" in str(path), \
            f"docs must be at governance_content/docs/, got: {path}"
        assert path.exists(), f"docs must exist at: {path}"

    def test_profiles_path_points_to_governance_content_profiles(self):
        """Happy: profiles are at governance_content/profiles/."""
        from tests.util import get_profiles_path
        path = get_profiles_path()
        assert "governance_content/profiles" in str(path), \
            f"profiles must be at governance_content/profiles/, got: {path}"
        assert path.exists(), f"profiles must exist at: {path}"

    def test_templates_path_points_to_governance_content_templates(self):
        """Happy: templates are at governance_content/templates/."""
        from tests.util import get_templates_path
        path = get_templates_path()
        assert "governance_content/templates" in str(path), \
            f"templates must be at governance_content/templates/, got: {path}"
        assert path.exists(), f"templates must exist at: {path}"

    def test_rulesets_path_points_to_governance_spec_rulesets(self):
        """Happy: rulesets are at governance_spec/rulesets/."""
        from tests.util import get_rulesets_path
        path = get_rulesets_path()
        assert "governance_spec/rulesets" in str(path), \
            f"rulesets must be at governance_spec/rulesets/, got: {path}"
        assert path.exists(), f"rulesets must exist at: {path}"

    def test_governance_runtime_exists_as_migration_target(self):
        """Happy: governance_runtime/ exists as the migration target."""
        runtime_path = REPO_ROOT / "governance_runtime"
        assert runtime_path.is_dir(), "governance_runtime/ must exist as migration target"
        
        expected_subdirs = ["application", "domain", "engine", "infrastructure", "kernel"]
        for subdir in expected_subdirs:
            subdir_path = runtime_path / subdir
            assert subdir_path.is_dir(), f"governance_runtime/{subdir}/ must exist"
