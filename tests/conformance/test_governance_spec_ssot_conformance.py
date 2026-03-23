"""
Governance Spec SSOT Conformance Test

Validates that governance_spec/ contains all required specification files
at the final SSOT location.
"""
from __future__ import annotations

import pytest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.conformance
class TestGovernanceSpecSSOT:
    """Validate governance_spec/ contains all required specification files."""

    def test_phase_api_yaml_exists_in_governance_spec(self):
        """Happy: phase_api.yaml exists in governance_spec/."""
        spec_path = REPO_ROOT / "governance_spec" / "phase_api.yaml"
        assert spec_path.is_file(), "phase_api.yaml must exist in governance_spec/"

    def test_rules_yml_exists_in_governance_spec(self):
        """Happy: rules.yml exists in governance_spec/."""
        spec_path = REPO_ROOT / "governance_spec" / "rules.yml"
        assert spec_path.is_file(), "rules.yml must exist in governance_spec/"

    def test_rulesets_directory_exists_in_governance_spec(self):
        """Happy: rulesets/ directory exists in governance_spec/."""
        spec_path = REPO_ROOT / "governance_spec" / "rulesets"
        assert spec_path.is_dir(), "rulesets/ must exist in governance_spec/"

    def test_rulesets_core_exists(self):
        """Happy: rulesets/core/ exists."""
        core_path = REPO_ROOT / "governance_spec" / "rulesets" / "core"
        assert core_path.is_dir(), "rulesets/core/ must exist"

    def test_rulesets_profiles_exists(self):
        """Happy: rulesets/profiles/ exists."""
        profiles_path = REPO_ROOT / "governance_spec" / "rulesets" / "profiles"
        assert profiles_path.is_dir(), "rulesets/profiles/ must exist"

    def test_schemas_directory_exists_in_governance_spec(self):
        """Happy: schemas/ directory exists in governance_spec/."""
        schemas_path = REPO_ROOT / "governance_spec" / "schemas"
        assert schemas_path.is_dir(), "schemas/ must exist in governance_spec/"

    def test_contracts_directory_exists_in_governance_spec(self):
        """Happy: contracts/ directory exists in governance_spec/."""
        contracts_path = REPO_ROOT / "governance_spec" / "contracts"
        assert contracts_path.is_dir(), "contracts/ must exist in governance_spec/"

    def test_config_directory_exists_in_governance_spec(self):
        """Happy: config/ directory exists in governance_spec/."""
        config_path = REPO_ROOT / "governance_spec" / "config"
        assert config_path.is_dir(), "config/ must exist in governance_spec/"
